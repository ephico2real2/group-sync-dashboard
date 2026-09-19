"""Playwright tests for the dashboard UI.

These run against a *seeded* app instance with the poller disabled, not against a live
cluster. That is deliberate: the states worth testing hardest — an overdue CR, a cluster
whose token is rejected, a current reconcile error — are exactly the ones a healthy cluster
never shows, and a live cluster's counts change under the test while it runs.

A separate smoke test (test_live_smoke.py) covers the real thing.
"""

from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import socket
import threading
import time
from datetime import UTC, datetime, timedelta

import httpx
import urllib.parse

import pytest
import uvicorn

from gsd import loginlog
from gsd.api import build_app
from gsd.config import ClusterConfig, Settings
from gsd.logincapture import event_dict
from gsd.loginlog import LoginAttempt
from gsd.store import Store


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


#: Rows the Groups tab lists for the seeded cluster. Named because eight tests use it as their proxy
#: for "we are back on the group list", and a bare 3 gave no clue what the fourth row was when the
#: login-gate group arrived.
#:
#: FOUR, and the fourth is the gate group. It is a synced Group like any other — pulled by its own CR,
#: carrying its DN in ldap_uid — so listing it is correct: omitting a real object because it happens to
#: grant login rather than access would be a lie by omission. It produces no false finding either; it
#: has a sync_provider (so not "unattributed") and members (so not "empty").
SYNCED_GROUPS = 4


def _seed(db_path: str) -> None:
    """Seed a store covering every state the UI must render distinctly."""
    now = datetime.now(UTC)
    store = Store(db_path)

    store.upsert_cluster("crc-local", "https://api.crc.testing:6443", True)
    store.upsert_cluster("prod-east", "https://api.prod-east.example.com:6443", True)

    store.record_poll("crc-local", "ok", None)
    # A cluster whose token expired must degrade to a card, never blank the page.
    store.record_poll("prod-east", "auth_failed", "401 Unauthorized — token invalid or expired")

    store.replace_groupsync_state(
        "crc-local",
        [
            {
                "name": "ldap-groupsync",
                "namespace": "group-sync-operator",
                "schedule": "*/30 * * * *",
                "ldap_filter": "(&(objectClass=groupOfNames)(cn=app-ocp-rbac-*))",
                "last_sync_at": _iso(now - timedelta(minutes=4)),
                "generation": 2,
                "provider_keys": ["ldap-groupsync_ldap"],
            },
            {
                # Hours past two hourly intervals -> overdue.
                "name": "bda-rbac-groupsync",
                "namespace": "group-sync-operator",
                "schedule": "0 * * * *",
                "ldap_filter": "(&(objectClass=groupOfNames)(cn=bda-rbac-*))",
                "last_sync_at": _iso(now - timedelta(hours=6)),
                "generation": 2,
                "provider_keys": ["bda-rbac-groupsync_ldap"],
            },
        ],
        _iso(now),
    )

    # A stale error (superseded by a later success) and a current one, so the UI's
    # distinction between them is exercised in both directions.
    store.upsert_reconcile_error(
        "crc-local", "ldap-groupsync", _iso(now - timedelta(days=2)), 1,
        'failed calling webhook "validate.kyverno.svc-fail": connection refused',
    )
    store.upsert_reconcile_error(
        "crc-local", "bda-rbac-groupsync", _iso(now - timedelta(minutes=2)), 2,
        "LDAP bind failed: invalid credentials",
    )

    store.replace_group_state(
        "crc-local",
        [
            {"name": "app-ocp-rbac-alpha-ns-admin", "member_count": 2,
             "sync_provider": "ldap-groupsync_ldap",
             "group_synced_at": _iso(now - timedelta(minutes=4)),
             "ldap_uid": "cn=app-ocp-rbac-alpha-ns-admin,ou=Groups,dc=ephico2real,dc=com"},
            {"name": "app-ocp-rbac-abcd-ns-superuser", "member_count": 0,
             "sync_provider": "ldap-groupsync_ldap",
             "group_synced_at": _iso(now - timedelta(minutes=4)),
             "ldap_uid": "cn=app-ocp-rbac-abcd-ns-superuser,ou=Groups,dc=ephico2real,dc=com"},
            {"name": "gsd-test-unattributed", "member_count": 0,
             "sync_provider": None, "group_synced_at": None, "ldap_uid": None},
        ],
        _iso(now),
    )

    # Membership across two polls, so the UI has both current members and a change to show:
    # bob leaves the admin group, dave joins. Both are silent on the cluster.
    store.sync_members(
        "crc-local",
        {
            "app-ocp-rbac-alpha-ns-admin": ["alice", "bob"],
            "app-ocp-rbac-abcd-ns-superuser": [],
            "gsd-test-unattributed": [],
            # Present in history, never in group_state -> a group deleted from the cluster.
            # Still reachable from every change row that names it.
            "app-ocp-rbac-gone-ns-viewer": ["alice"],
        },
        {"app-ocp-rbac-alpha-ns-admin": _iso(now - timedelta(hours=1))},
        _iso(now - timedelta(hours=1)),
    )
    store.sync_members(
        "crc-local",
        {
            "app-ocp-rbac-alpha-ns-admin": ["alice", "dave"],
            "app-ocp-rbac-abcd-ns-superuser": [],
            "gsd-test-unattributed": [],
        },
        {"app-ocp-rbac-alpha-ns-admin": _iso(now - timedelta(minutes=4))},
        _iso(now - timedelta(minutes=4)),
    )

    # The User objects — the people who have LOGGED IN, which is what the Users tab lists
    # (docs/DESIGN_users_tab_logins.md). The real shape, measured on the reference cluster:
    #   alice       logged in, named, in a synced group
    #   gatekeeper  logged in, provider supplied no name, in the gate group only
    #   kubeadmin   logged in, in NO synced group — the "logged in, no synced access" row
    #   dave        a synced member who has NEVER logged in: no User object, so not a row here,
    #               reported on the tab as one line and rendered as a bare id on every member surface.
    store.replace_users("crc-local", [
        {"user_name": "alice", "full_name": "Alice Cooper", "created_at": _iso(now - timedelta(days=30)),
         "providers": ["ldap-local"], "has_identity": True},
        {"user_name": "gatekeeper", "full_name": None, "created_at": _iso(now - timedelta(days=2)),
         "providers": ["ldap-local"], "has_identity": True},
        {"user_name": "kubeadmin", "full_name": None, "created_at": _iso(now - timedelta(days=400)),
         "providers": ["developer"], "has_identity": True},
    ], _iso(now), identity_created={"alice": _iso(now - timedelta(days=29))})

    # Bindings covering all three finding tiers: one genuinely broken, one that names a
    # group which never existed, and the built-in noise that must not drown them.
    store.record_managed_groups(
        "crc-local", [{"name": "was-managed", "sync_provider": "ldap-groupsync_ldap"},
                      {"name": "app-ocp-rbac-alpha-ns-admin",
                       "sync_provider": "ldap-groupsync_ldap"}],
        _iso(now - timedelta(days=1)),
    )
    store.replace_bindings(
        "crc-local",
        [
            {"binding_kind": "RoleBinding", "binding_namespace": "prod-ns",
             "binding_name": "was-managed-rb", "role_kind": "ClusterRole",
             "role_name": "admin", "group_name": "was-managed"},
            {"binding_kind": "RoleBinding", "binding_namespace": "klt-pass-both",
             "binding_name": "klta-audit-rb", "role_kind": "ClusterRole",
             "role_name": "view", "group_name": "app-ocp-rbac-klta-ns-audit"},
            # Operator-templated: its presence is what proves this cluster uses the policy
            # system at all, which the `unmanaged` finding requires before flagging anything.
            {"binding_kind": "RoleBinding", "binding_namespace": "prod-ns",
             "binding_name": "managed-admin-rb", "role_kind": "ClusterRole",
             "role_name": "admin", "group_name": "app-ocp-rbac-alpha-ns-admin",
             "managed_source": "prod-rbac"},
            # Hand-made on a synced group -> `unmanaged`.
            {"binding_kind": "ClusterRoleBinding", "binding_namespace": "",
             "binding_name": "hand-made-crb", "role_kind": "ClusterRole",
             "role_name": "cluster-admin", "group_name": "app-ocp-rbac-alpha-ns-admin"},
        ]
        + [
            {"binding_kind": "RoleBinding", "binding_namespace": f"ns{i}",
             "binding_name": f"pullers-{i}", "role_kind": "ClusterRole",
             "role_name": "system:image-puller",
             "group_name": f"system:serviceaccounts:ns{i}"}
            for i in range(6)
        ],
        _iso(now),
    )

    # The policy operator: one healthy CR and one currently failing, so the RBAC-policy
    # page renders both states and the alert path is exercised.
    store.replace_operator_configs(
        "crc-local",
        [
            {"kind": "GroupConfig", "name": "cluster-admin-groupconfig-rbac",
             "error_at": None, "error_message": None, "success_at": _iso(now)},
            {"kind": "NamespaceConfig", "name": "multitenant",
             "error_at": _iso(now - timedelta(minutes=1)),
             "error_message": "failed calling webhook validate.kyverno.svc-fail",
             "success_at": _iso(now - timedelta(days=1))},
        ],
        _iso(now),
    )

    # Direct user grants — the whole subject of the Namespace-audit tab, which had no
    # browser test at all. Two things here are load-bearing:
    #   * jdoe holds grants in TWO namespaces, so a "People exposed" that sums per-namespace
    #     distinct_users reports 3 where the truth is 2. That is the bug that shipped.
    #   * jdoe's name is an LDAP DN, which is what OpenShift produces when the identity
    #     provider maps `dn`. It contains commas, so any user list built by splitting a
    #     delimited string reports that one person as four.
    # #167: every namespace the poller sees, with the captured labels — the grants above reach some
    store.replace_namespaces("crc-local", [
        {"name": "prod-ns", "created_at": _iso(now - timedelta(days=90)), "phase": "Active",
         "metadata": {"company.net/mnemonic": "demo", "company.net/app-environment": "prod"}},
        {"name": "klt-pass-both", "created_at": _iso(now - timedelta(days=30)), "phase": "Active",
         "metadata": {"company.net/mnemonic": "klt", "company.net/app-environment": "qa"}},
        {"name": "quiet-corner", "created_at": _iso(now - timedelta(days=10)), "phase": "Active",
         "metadata": {"company.net/mnemonic": "demo", "company.net/app-environment": "qa"}},
        *[{"name": f"ns{i}", "created_at": _iso(now - timedelta(days=5)), "phase": "Active", "metadata": {}} for i in range(6)],
    ], _iso(now))
    store.replace_user_bindings(
        "crc-local",
        [
            {"binding_kind": "RoleBinding", "binding_namespace": "prod-ns",
             "binding_name": "jdoe-admin", "role_kind": "ClusterRole", "role_name": "admin",
             "user_name": "cn=jdoe,ou=people,dc=ephico2real,dc=com", "is_platform": 0},
            {"binding_kind": "RoleBinding", "binding_namespace": "dev-ns",
             "binding_name": "jdoe-edit", "role_kind": "ClusterRole", "role_name": "edit",
             "user_name": "cn=jdoe,ou=people,dc=ephico2real,dc=com", "is_platform": 0},
            {"binding_kind": "ClusterRoleBinding", "binding_namespace": "",
             "binding_name": "carol-ca", "role_kind": "ClusterRole",
             "role_name": "cluster-admin", "user_name": "carol", "is_platform": 0},
            # Excluded by default and counted separately: there is nowhere to migrate it to.
            {"binding_kind": "ClusterRoleBinding", "binding_namespace": "",
             "binding_name": "ka", "role_kind": "ClusterRole", "role_name": "cluster-admin",
             "user_name": "kubeadmin", "is_platform": 1},
        ],
        _iso(now),
    )

    # ── The login-gate group ───────────────────────────────────────────────────────────────
    # A synced group like any other, carrying its DN in ldap_uid — which is how the dashboard
    # identifies it. Membership is deliberately NOT the same set as the RBAC groups above:
    #   alice   in the gate group AND in a synced RBAC group  -> healthy, no finding
    #   dave    in a synced RBAC group, NOT in the gate group -> holds access he cannot use
    #   gatekeeper  in the gate group only                    -> can log in, holds no access
    # bob is in neither now (removed from the RBAC group earlier), so he is not a finding here.
    GATE_DN = "cn=app-ssb-autobahnusers,ou=Groups,dc=ephico2real,dc=com"
    store.replace_group_state(
        "crc-local",
        [
            {"name": "app-ocp-rbac-alpha-ns-admin", "member_count": 2,
             "sync_provider": "ldap-groupsync_ldap",
             "group_synced_at": _iso(now - timedelta(minutes=4)),
             "ldap_uid": "cn=app-ocp-rbac-alpha-ns-admin,ou=Groups,dc=ephico2real,dc=com"},
            {"name": "app-ocp-rbac-abcd-ns-superuser", "member_count": 0,
             "sync_provider": "ldap-groupsync_ldap",
             "group_synced_at": _iso(now - timedelta(minutes=4)),
             "ldap_uid": "cn=app-ocp-rbac-abcd-ns-superuser,ou=Groups,dc=ephico2real,dc=com"},
            {"name": "gsd-test-unattributed", "member_count": 0,
             "sync_provider": None, "group_synced_at": None, "ldap_uid": None},
            {"name": "app-ssb-autobahnusers", "member_count": 2,
             "sync_provider": "ldap-clusteraccess-groupsync_ldap",
             "group_synced_at": _iso(now - timedelta(minutes=4)), "ldap_uid": GATE_DN},
        ],
        _iso(now),
    )
    store.sync_members(
        "crc-local",
        {
            "app-ocp-rbac-alpha-ns-admin": ["alice", "dave"],
            "app-ocp-rbac-abcd-ns-superuser": [],
            "gsd-test-unattributed": [],
            "app-ssb-autobahnusers": ["alice", "gatekeeper"],
        },
        {"app-ocp-rbac-alpha-ns-admin": _iso(now - timedelta(minutes=4))},
        _iso(now - timedelta(minutes=3)),
    )
    # Discovered rather than configured, so the panel's provenance chip is exercised. The DN is
    # matched against ldap_uid case-INSENSITIVELY, and the case here differs deliberately.
    store.set_cluster_access_group(
        "crc-local", "CN=app-ssb-autobahnusers,OU=Groups,DC=ephico2real,DC=com", "oauth",
        "app-ssb-autobahnusers", _iso(now))

    # ── Login attempts, one row per state the Logins tab must render distinctly ────────────
    # Built through logincapture.event_dict() from real LoginAttempt objects rather than
    # hand-written dicts, so the seed cannot drift from what the capture loop actually writes —
    # a UI test passing against a row shape the poller does not produce is worse than no test.
    #
    # The four accounts are chosen for what the PAGE has to distinguish:
    #   alice    — a current member of a synced group. Governed; must NOT appear as a finding.
    #   bob      — removed from every group and still trying. known_user 0, has_history 1: the
    #              offboarding that did not finish, which is the whole point of the feature.
    #   mallory  — a name this cluster has never governed. known_user 0, has_history 0, and so
    #              NOT drillable: /users/{name} 404s for her, and a link into an error card is
    #              worse than plain text.
    #   developer — a success on the HTPasswd provider. Labelled break-glass and excluded from
    #              the ungoverned list, because there is nowhere to migrate it to.
    # bob twice, so `attempts` is a count rather than always 1, and from two different pods so
    # the dedup key's pod_name component is exercised by a rendered row.
    attempts = [
        (LoginAttempt("alice", loginlog.OUTCOME_SUCCESS,
                      now - timedelta(minutes=12), provider="ldap-local"), "oauth-openshift-aaa"),
        (LoginAttempt("bob", loginlog.OUTCOME_BAD_PASSWORD,
                      now - timedelta(minutes=9), provider="ldap-local",
                      ldap_result_code=49), "oauth-openshift-aaa"),
        (LoginAttempt("bob", loginlog.OUTCOME_ACCOUNT_LOCKED,
                      now - timedelta(minutes=8), provider="ldap-local",
                      ldap_result_code=49, detail="AD sub-code 775: account locked"),
         "oauth-openshift-bbb"),
        # bob has membership history (he was removed from the admin group above), so the directory
        # knows him: a refusal for him resolves to `not_gated` rather than `no_record`.
        (LoginAttempt("bob", loginlog.OUTCOME_REJECTED,
                      now - timedelta(minutes=7), provider="ldap-local",
                      detail="no entries matching the provider's filter"), "oauth-openshift-aaa"),
        (LoginAttempt("mallory", loginlog.OUTCOME_REJECTED,
                      now - timedelta(minutes=6), provider="ldap-local",
                      detail="no entries matching the provider's filter"), "oauth-openshift-aaa"),
        (LoginAttempt("developer", loginlog.OUTCOME_SUCCESS,
                      now - timedelta(minutes=3), provider="developer"), "oauth-openshift-bbb"),
    ]
    store.record_login_events(
        "crc-local",
        [event_dict(a, pod, _iso(now)) for a, pod in attempts],
    )
    # Set once by the first read, and LATER than the oldest attempt on purpose: the first read
    # looks back an hour, so the record legitimately reaches BEHIND the moment watching began.
    # That makes capture_started_at later than retained_since, which looks like a bug and is not
    # — the page explains it, and this is the state that proves the explanation appears.
    store.record_login_read("crc-local", _iso(now - timedelta(minutes=10)))
    store.record_login_read("crc-local", _iso(now - timedelta(seconds=30)))
    # alice's display name is already seeded above via replace_users, so the Logins table gets
    # `alice · Alice Cooper` from the same ocp_user row every other member surface reads.

    # Enough events for the timeline to draw a line, with a count cliff in the middle.
    for i, count in enumerate([40, 41, 41, 28, 41]):
        ts = _iso(now - timedelta(minutes=30 * (5 - i)))
        store.record_sync_event(
            "crc-local", "ldap-groupsync", "group-sync-operator", ts, ts, "*/30 * * * *", count
        )
    store.close()


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    db = str(tmp_path_factory.mktemp("gsd") / "ui.db")
    _seed(db)
    settings = Settings(
        clusters=[
            ClusterConfig("crc-local", "https://api.crc.testing:6443", token_env="X"),
            ClusterConfig("prod-east", "https://api.prod-east.example.com:6443", token_env="Y"),
        ],
        db_path=db,
        # The Logins tab renders a "not being captured" card when this is off, which is a
        # different state from on-and-quiet. On, so the seeded attempts are what gets tested;
        # the off state has its own test that overrides it.
        login_capture_enabled=True,
        namespace_metadata_labels=("company.net/mnemonic", "company.net/app-environment"),
        # This fixture predates per-user visibility and its tests assert the WIDE view
        # with the proxy off. Proxy-off already serves wide (there is no trusted identity
        # to scope to), so turning restrictions off here records the same deliberate,
        # documented choice a proxyless deployment must make — instead of leaning on the
        # inert combination and its startup warning. The visibility labelling has its own
        # scoped_server fixture below, where restrictions stay on.
        view_restrictions_enabled=False,
    )
    port = _free_port()
    app = build_app(settings, run_poller=False)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    srv = uvicorn.Server(config)
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()

    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(f"{base}/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        raise RuntimeError("dashboard server did not start")

    yield base
    srv.should_exit = True
    thread.join(timeout=5)


@pytest.fixture()
def dash(page, server):
    """The dashboard, loaded, with an uncaught JS error treated as an immediate failure.

    Without the pageerror listener this suite reports a syntax error in index.html as a
    30-second selector timeout, once per test — so a single stray backtick inside a
    template literal (which is how this was found: the whole page rendered blank and the
    suite hung for minutes) looks like slowness rather than the total failure it is.

    The page is one file with no build step and no type checker, so this fixture is the
    only thing standing between a typo and a blank dashboard. It reports the actual
    exception text, which names the line.
    """
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    # #158 made Home the landing page, and these are the OVERVIEW's tests plus the tab walks that
    # start from it: the position is named rather than assumed, so a later change to the default
    # route cannot silently move what they assert. Home has its own fixture below.
    page.goto(f"{server}/#page=overview")
    try:
        page.wait_for_selector(".hero .value", timeout=10_000)
    except Exception:
        if errors:
            pytest.fail("the page raised and never rendered:\n  " + "\n  ".join(errors))
        raise
    assert not errors, "uncaught JS error on load:\n  " + "\n  ".join(errors)
    return page


class TestOverview:
    def test_hero_and_cluster_cards_render(self, dash):
        assert dash.locator(".hero .value").inner_text().strip().isdigit()
        headings = dash.locator("section.card h2").all_inner_texts()
        assert {"crc-local", "prod-east"} <= set(headings)
        assert "GroupSync CRs" in headings

    def test_unreachable_cluster_degrades_to_a_card_not_a_page_error(self, dash):
        """PLAN §5: one bad token must not blank the dashboard."""
        body = dash.locator("body").inner_text()
        assert "401 Unauthorized" in body          # the failure is shown...
        assert "crc-local" in body                 # ...and the healthy cluster still renders
        assert dash.locator("table").count() >= 1  # ...along with its data

    def test_state_is_never_conveyed_by_colour_alone(self, dash):
        """good vs critical is deutan ΔE 4.1 — green and red are near-identical to a
        deuteranope, so every badge carries a text label and a distinct glyph shape."""
        badges = dash.locator(".badge")
        assert badges.count() > 0
        for i in range(badges.count()):
            text = badges.nth(i).inner_text().strip()
            assert text, "a badge rendered with no text label"
            assert badges.nth(i).locator(".glyph").count() == 1

    def test_alerts_use_severity_words_not_cr_state_words(self, dash):
        """Caught by screenshotting: the alert list reused the CR-state badge, so an
        `auth_failed` cluster and a failed reconcile both rendered a badge reading
        'overdue'. The label is the channel a colourblind reader relies on, so a wrong
        label is a correctness bug, not a cosmetic one.
        """
        labels = [
            dash.locator(".alert-row .badge").nth(i).inner_text().strip()
            for i in range(dash.locator(".alert-row .badge").count())
        ]
        assert labels, "no alerts rendered"
        assert set(labels) <= {"critical", "warning"}, f"state words leaked into alerts: {labels}"

    def test_reconcile_error_badge_says_what_it_is(self, dash):
        row = dash.locator("tr[data-cr='bda-rbac-groupsync']")
        assert "reconcile error" in row.inner_text()

    def test_overdue_cr_is_shown_as_overdue(self, dash):
        row = dash.locator("tr", has_text="bda-rbac-groupsync")
        assert "overdue" in row.first.inner_text()

    def test_healthy_cr_is_shown_as_ok(self, dash):
        row = dash.locator("tr", has_text="ldap-groupsync")
        assert "ok" in row.first.inner_text()

    def test_next_expected_distinguishes_the_two_schedules(self, dash):
        """`0 * * * *` and `*/30 * * * *` look identical if you only measure gaps."""
        body = dash.locator("body").inner_text()
        assert "0 * * * *" in body and "*/30 * * * *" in body


class TestGroupSyncDetail:
    def test_clicking_a_row_opens_detail_with_a_timeline(self, dash):
        dash.locator("tr[data-cr='ldap-groupsync']").click()
        dash.wait_for_selector("svg .series-line")
        assert dash.locator("svg circle.dot").count() == 5
        assert "Observed syncs" in dash.locator("body").inner_text()

    def test_timeline_values_are_also_in_a_table(self, dash):
        """A tooltip must never be the only way to read a value."""
        dash.locator("tr[data-cr='ldap-groupsync']").click()
        dash.wait_for_selector("svg .series-line")
        text = dash.locator("body").inner_text()
        assert "28" in text, "the count cliff must be readable without hovering"

    def test_stale_reconcile_error_is_labelled_stale(self, dash):
        """PLAN §2.1: ReconcileError stays True forever, so an unqualified error banner
        would paint a healthy CR permanently red."""
        dash.locator("tr[data-cr='ldap-groupsync']").click()
        dash.wait_for_selector("svg .series-line")
        body = dash.locator("body").inner_text()
        assert "stale, superseded by a later success" in body

    def test_current_reconcile_error_is_labelled_current(self, dash):
        dash.locator("tr[data-cr='bda-rbac-groupsync']").click()
        dash.wait_for_selector("text=Last reconcile error")
        assert "current" in dash.locator("body").inner_text()
        assert "LDAP bind failed" in dash.locator("body").inner_text()

    def test_back_returns_to_overview(self, dash):
        dash.locator("tr[data-cr='ldap-groupsync']").click()
        dash.wait_for_selector("#back")
        dash.locator("#back").click()
        dash.wait_for_selector(".hero .value")
        assert dash.locator("tr[data-cr]").count() == 2


class TestGroupExplorer:
    def _open_groups(self, dash):
        dash.locator("button[data-nav='groups']").click()
        # A DATA row, not the filter chrome: the tab handler paints the destination before
        # it fetches (2026-08-10), so #f-state now appears immediately and no longer means
        # "the fetch landed". Only a fetched render produces tr[data-group].
        dash.wait_for_selector("tr[data-group]")

    def test_all_groups_listed(self, dash):
        self._open_groups(dash)
        assert dash.locator("tbody tr").count() == SYNCED_GROUPS

    def test_empty_filter_includes_the_unmanaged_group(self, dash):
        """EMPTY is 'zero members', whatever created the group.

        Both seeded memberless groups appear: one operator-synced, one hand-made. The hand-made
        one is also under `unattributed` — the two filters overlap by design, because on a
        cluster with no operator a provider-scoped `empty` matched nothing at all.
        """
        self._open_groups(dash)
        dash.select_option("#f-state", "empty")
        dash.wait_for_function("document.querySelectorAll('tbody tr').length === 2")
        text = dash.locator("tbody").inner_text()
        assert "app-ocp-rbac-abcd-ns-superuser" in text
        assert "gsd-test-unattributed" in text

    def test_unattributed_filter(self, dash):
        self._open_groups(dash)
        dash.select_option("#f-state", "unattributed")
        dash.wait_for_function("document.querySelectorAll('tbody tr').length === 1")
        assert "gsd-test-unattributed" in dash.locator("tbody").inner_text()

    def test_source_dn_is_shown(self, dash):
        self._open_groups(dash)
        assert "ou=Groups,dc=ephico2real,dc=com" in dash.locator("tbody").inner_text()

    def test_rows_are_zebra_striped(self, dash):
        """Striping is what makes a 60-row table scannable; it must actually render."""
        self._open_groups(dash)
        rows = dash.locator("tbody tr")
        odd = rows.nth(0).locator("td").first.evaluate("e => getComputedStyle(e).backgroundColor")
        even = rows.nth(1).locator("td").first.evaluate("e => getComputedStyle(e).backgroundColor")
        assert odd != even, "adjacent rows render identically — no striping"

    def test_owner_colour_is_accompanied_by_the_name(self, dash):
        """Hue is the fast channel, never the only one.

        The dot is wanted, but it must stay a supplement: a reader who cannot separate the
        hues has to get the same answer from the text sitting beside it.
        """
        self._open_groups(dash)
        owner = dash.locator("tbody .owner").first
        assert owner.locator(".cr-dot").count() == 1
        assert owner.inner_text().strip(), "owner dot with no name beside it"


class TestGroupDrilldown:
    def _open_group(self, dash, name):
        dash.locator("button[data-nav='groups']").click()
        dash.wait_for_selector("tr[data-group]")
        dash.locator(f"tr[data-group='{name}']").click()
        dash.wait_for_selector("#back-groups")

    def test_members_are_listed_with_join_time(self, dash):
        self._open_group(dash, "app-ocp-rbac-alpha-ns-admin")
        body = dash.locator("body").inner_text()
        assert "alice" in body and "dave" in body
        assert "Member since" in body

    def test_departed_member_is_not_shown_as_current(self, dash):
        """bob left in the second poll; he belongs in the change log, not the member list."""
        self._open_group(dash, "app-ocp-rbac-alpha-ns-admin")
        members = dash.locator("tr[data-user]").all_inner_texts()
        assert not any("bob" in m for m in members)

    def test_membership_changes_show_both_directions(self, dash):
        """A user quietly dropping out is the invisible absence this view exists for."""
        self._open_group(dash, "app-ocp-rbac-alpha-ns-admin")
        body = dash.locator("body").inner_text()
        assert "joined" in body and "left" in body
        assert "bob" in body, "the departure must still be visible in the change log"

    def test_empty_group_explains_itself(self, dash):
        self._open_group(dash, "app-ocp-rbac-abcd-ns-superuser")
        assert "no members" in dash.locator("body").inner_text().lower()

    def test_back_returns_to_the_group_list(self, dash):
        self._open_group(dash, "app-ocp-rbac-alpha-ns-admin")
        dash.locator("#back-groups").click()
        # Wait on something unique to the list view: #f-state is present in both, so
        # waiting on it returns instantly and reads the pre-render DOM.
        dash.wait_for_function("() => !document.querySelector('#back-groups')")
        assert dash.locator("tbody tr").count() == SYNCED_GROUPS

    def test_member_names_look_drillable(self, dash):
        """Regression: the click handler worked but the names rendered as plain black text
        identical to every other cell, so nothing invited the click. A selector-driven test
        cannot notice that, which is exactly why this asserts the affordance itself.
        """
        self._open_group(dash, "app-ocp-rbac-alpha-ns-admin")
        name = dash.locator("tr[data-user='alice'] .drill").first
        assert name.count() == 1, "member name carries no drill affordance"
        colour = name.evaluate("e => getComputedStyle(e).color")
        plain = dash.locator("h2").first.evaluate("e => getComputedStyle(e).color")
        assert colour != plain, "drillable name is styled the same as ordinary text"
        assert name.evaluate("e => getComputedStyle(e).cursor") == "pointer"

    def test_members_table_says_the_names_are_clickable(self, dash):
        self._open_group(dash, "app-ocp-rbac-alpha-ns-admin")
        assert "Select a user" in dash.locator("body").inner_text()

    def test_a_member_who_has_logged_in_shows_their_display_name(self, dash):
        """The id stays the primary text; the name is secondary.

        That order is deliberate rather than cosmetic: this page is read next to `oc` output, and
        the id is what you type. It is also what keeps `data-user` and the drill button matching
        the id, which several other tests here rely on.
        """
        self._open_group(dash, "app-ocp-rbac-alpha-ns-admin")
        row = dash.locator("tr[data-user='alice']").first.inner_text()
        assert "alice" in row, "the user id must remain the primary text"
        assert "Alice Cooper" in row, "a known display name is not shown"
        assert row.index("alice") < row.index("Alice Cooper"), (
            "the id must come first — the name is the subordinate text, not the heading"
        )

    def test_a_member_who_has_never_logged_in_renders_exactly_as_before(self, dash):
        """The ordinary case: no User object, so no name, and no separator or empty span.

        3 of 10 members on the reference cluster are in this state, one of whom has no directory
        entry at all and can never leave it. A stray "·" on every one of those rows would be a
        permanent visual defect on the majority of some clusters' member lists.
        """
        self._open_group(dash, "app-ocp-rbac-alpha-ns-admin")
        row = dash.locator("tr[data-user='dave']").first.inner_text()
        assert "dave" in row
        assert "·" not in row, (
            "an unnamed member must render the bare id, with no leftover separator"
        )

    def test_the_user_page_heading_carries_both_id_and_name(self, dash):
        self._open_group(dash, "app-ocp-rbac-alpha-ns-admin")
        dash.locator("tr[data-user='alice'] .drill").first.click()
        dash.wait_for_selector("text=Group memberships")
        heading = dash.locator("h2").first.inner_text()
        assert "alice" in heading and "Alice Cooper" in heading

    def test_the_user_page_heading_of_an_unnamed_user_is_unchanged(self, dash):
        """bob never logged in, so his page must look exactly as it did before this feature."""
        self._open_group(dash, "app-ocp-rbac-alpha-ns-admin")
        dash.locator(".drill[data-user='bob']").first.click()
        dash.wait_for_selector("text=Group memberships")
        heading = dash.locator("h2").first.inner_text()
        assert "bob" in heading and "·" not in heading

    def test_departed_user_is_drillable_from_the_change_log(self, dash):
        """A user who left appears ONLY in the change log — which is precisely when you
        want to check what else they still belong to."""
        self._open_group(dash, "app-ocp-rbac-alpha-ns-admin")
        bob = dash.locator(".drill[data-user='bob']").first
        assert bob.count() == 1, "departed user is not drillable"
        bob.click()
        dash.wait_for_selector("text=Group memberships")
        assert "bob" in dash.locator("h2").first.inner_text()

    def test_drill_works_from_the_keyboard(self, dash):
        self._open_group(dash, "app-ocp-rbac-alpha-ns-admin")
        name = dash.locator("tr[data-user='alice'] .drill").first
        name.focus()
        name.press("Enter")
        dash.wait_for_selector("text=Group memberships")
        assert "alice" in dash.locator("h2").first.inner_text()

    def test_user_reverse_lookup(self, dash):
        """"Why does this person have access?" — click a member, see every group."""
        self._open_group(dash, "app-ocp-rbac-alpha-ns-admin")
        dash.locator("tr[data-user='alice']").click()
        # Both views carry #back-groups, so wait for the user view's own heading.
        dash.wait_for_selector("text=Group memberships")
        body = dash.locator("body").inner_text()
        assert "alice" in body
        assert "app-ocp-rbac-alpha-ns-admin" in body
        assert "Group memberships" in body


class TestRendering:
    def test_no_horizontal_page_scroll(self, dash):
        """Wide tables scroll inside their own container, not the page body."""
        overflow = dash.evaluate(
            "() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        assert overflow <= 0, f"page scrolls horizontally by {overflow}px"

    def test_renders_in_dark_mode(self, dash):
        dash.evaluate("() => document.documentElement.setAttribute('data-theme','dark')")
        bg = dash.evaluate("() => getComputedStyle(document.body).backgroundColor")
        assert bg == "rgb(13, 13, 13)", f"dark surface not applied, got {bg}"

    def test_no_console_errors(self, server, page):
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(f"{server}/#page=overview")   # this test's subject is the Overview's chart (#158 moved the landing page)
        page.wait_for_selector(".hero .value")
        page.locator("tr[data-cr='ldap-groupsync']").click()
        page.wait_for_selector("svg .series-line")
        assert errors == []


class TestNavigationTrail:
    """Reported from the field: Back jumped to a fixed page instead of retracing, and a
    404 replaced the whole page including the Back button, stranding the reader."""

    def _open_group(self, dash, name):
        dash.locator("button[data-nav='groups']").click()
        dash.wait_for_selector("tr[data-group]")
        dash.locator(f"tr[data-group='{name}']").click()
        dash.wait_for_selector("#back-groups")

    def test_back_retraces_group_then_user(self, dash):
        """group -> user -> Back must land on the GROUP, not the group list."""
        self._open_group(dash, "app-ocp-rbac-alpha-ns-admin")
        dash.locator("tr[data-user='alice']").click()
        dash.wait_for_selector("text=Group memberships")
        assert "alice" in dash.locator("h2").first.inner_text()

        dash.locator("#back-groups").click()
        dash.wait_for_selector("text=Membership changes")
        assert "app-ocp-rbac-alpha-ns-admin" in dash.locator("h2").first.inner_text()

    def test_back_label_names_the_destination(self, dash):
        """A back button that says where it goes is what makes a trail usable."""
        self._open_group(dash, "app-ocp-rbac-alpha-ns-admin")
        dash.locator("tr[data-user='alice']").click()
        dash.wait_for_selector("text=Group memberships")
        assert "app-ocp-rbac-alpha-ns-admin" in dash.locator("#back-groups").inner_text()

    def test_back_twice_returns_to_the_list(self, dash):
        self._open_group(dash, "app-ocp-rbac-alpha-ns-admin")
        dash.locator("tr[data-user='alice']").click()
        dash.wait_for_selector("text=Group memberships")
        dash.locator("#back-groups").click()
        dash.wait_for_selector("text=Membership changes")
        dash.locator("#back-groups").click()
        dash.wait_for_function("() => !document.querySelector('#back-groups')")
        assert dash.locator("tbody tr").count() == SYNCED_GROUPS

    def test_nav_button_clears_the_trail(self, dash):
        """Jumping to a section is a fresh start, not a continuation of the old path."""
        self._open_group(dash, "app-ocp-rbac-alpha-ns-admin")
        dash.locator("tr[data-user='alice']").click()
        dash.wait_for_selector("text=Group memberships")
        dash.locator("button[data-nav='groups']").click()
        dash.wait_for_function("() => !document.querySelector('#back-groups')")
        assert dash.locator("tbody tr").count() == SYNCED_GROUPS

    def test_error_page_still_offers_a_way_back(self, dash):
        """The reported dead end: a 404 replaced the page, back button included."""
        self._open_group(dash, "app-ocp-rbac-alpha-ns-admin")
        dash.evaluate("""() => {
            navigate({ group: 'definitely-not-a-real-group-xyz' });  // what a real click does
            refresh();
        }""")
        dash.wait_for_selector("text=Dashboard API error")
        assert dash.locator("#back-groups").count() == 1, "no way back from the error"
        dash.locator("#back-groups").click()
        dash.wait_for_selector("text=Membership changes")
        assert "app-ocp-rbac-alpha-ns-admin" in dash.locator("h2").first.inner_text()


class TestDeletedGroup:
    def test_deleted_group_renders_its_history_instead_of_404(self, dash):
        """Reported from the field: clicking a group named in a change row, after the group
        had been deleted, returned 404 and replaced the page. "This group is gone, here is
        who was in it" is the answer to that click."""
        dash.locator("button[data-nav='groups']").click()
        dash.wait_for_selector("tr[data-group]")
        dash.evaluate("""() => {
            navigate({ group: 'app-ocp-rbac-gone-ns-viewer' });
            refresh();
        }""")
        dash.wait_for_selector("text=Membership changes")
        body = dash.locator("body").inner_text()
        assert "deleted" in body.lower()
        assert "alice" in body, "the history of who was in it must survive"
        assert "Dashboard API error" not in body

    def test_back_works_from_a_deleted_group(self, dash):
        dash.locator("button[data-nav='groups']").click()
        dash.wait_for_selector("tr[data-group]")
        dash.evaluate("""() => {
            navigate({ group: 'app-ocp-rbac-gone-ns-viewer' });
            refresh();
        }""")
        dash.wait_for_selector("#back-groups")
        dash.locator("#back-groups").click()
        dash.wait_for_function("() => !document.querySelector('#back-groups')")
        assert dash.locator("tbody tr").count() == SYNCED_GROUPS


class TestBindingFindingsVisible:
    """The findings existed only on the API. A UI-only operator saw "No alerts" and
    concluded nothing was wrong, while bindings granted nobody — which is exactly the
    invisible-absence failure this dashboard is built to prevent."""

    def _open(self, dash):
        dash.locator("button[data-nav='bindings']").click()
        dash.wait_for_selector("text=grant nobody")

    def test_findings_are_reachable_from_the_nav(self, dash):
        assert dash.locator("button[data-nav='bindings']").count() == 1
        self._open(dash)

    def test_the_default_view_shows_what_was_granted_under_what_needs_review(self, dash):
        """The page is called Access granted and used to open on the faults alone; the bindings
        that actually grant access sat behind the filter, and the operator read the page as
        missing its data (enhancement, 2026-09-03). Faults stay on top; Granted follows; the
        built-in majority stays one filter away."""
        self._open(dash)
        assert dash.evaluate("() => view.bindingFilter") == "review"
        # Headings carry a severity badge and a count ("unresolved Unresolved · 1"), so match by word.
        headings = [h.strip() for h in dash.locator("#main section.card h2").all_inner_texts()]
        def at(word):
            hits = [i for i, h in enumerate(headings) if word in h.split()]
            assert hits, (word, headings)
            return hits[0]
        assert at("Granted") > at("Unresolved"), ("faults first, then what was granted", headings)
        assert not any("Built-in" in h for h in headings), "built-in bindings are noise to a reviewer and stay behind the filter"
        # The fixture's one healthy grant: a RoleBinding on a group that exists.
        granted = dash.locator("section.card:has(h2:has-text('Granted')) tbody tr")
        assert granted.count() >= 1
        assert "app-ocp-rbac-alpha-ns-admin" in granted.first.inner_text()
        assert "managed-admin-rb" in granted.first.inner_text()
        # The review hero is still the first thing on the page.
        assert "grant nobody" in dash.locator("#main").inner_text()
        assert "grant a real group follow" in dash.locator("#main").inner_text()
        assert dash.locator("#f-binding option[value='review']").inner_text().strip() == "granted + needs review"

    def test_each_granted_row_says_who_it_reaches(self, dash):
        """2 members · 1 logged in: alice has a User with an identity, dave has no User at all."""
        self._open(dash)
        row = dash.locator("section.card:has(h2:has-text('Granted')) tbody tr").first.inner_text()
        assert "2 members" in row and "1 logged in" in row, row
        # A row whose group has no object says nothing, not "0".
        unresolved = dash.locator("section.card:has(h2:has-text('Unresolved')) tbody tr").first.inner_text()
        assert "—" in unresolved and "members" not in unresolved, unresolved
        dash.select_option("#f-binding", "built_in")
        dash.wait_for_function("() => document.body.innerText.includes('system:serviceaccounts:ns0')")
        cells = dash.locator("tbody tr td:nth-child(2)").all_inner_texts()
        assert cells and all(c.strip() == "—" for c in cells), cells
        dash.select_option("#f-binding", "review")
        dash.wait_for_selector("text=grant nobody")

    def test_the_rbac_policy_page_shares_the_reaches_column(self, dash):
        dash.locator("button[data-nav='policy']").click()
        dash.wait_for_selector("section.card:has(h2:has-text('Grants outside')) tbody tr")
        row = dash.locator("section.card:has(h2:has-text('Grants outside')) tbody tr").first.inner_text()
        assert "2 members" in row and "1 logged in" in row, row
        self._open(dash)

    def test_an_old_servers_rows_render_a_dash_without_a_page_error(self, dash):
        self._open(dash)
        errors = []
        dash.on("pageerror", lambda e: errors.append(str(e)))
        dash.evaluate("""() => {
            const strip = (rows) => rows.map(({ member_count, logged_in_count, ...rest }) => rest);
            const d = data.findings;
            data.findings = Object.assign({}, d, { ok: strip(d.ok), unmanaged: strip(d.unmanaged) });
            render();
        }""")
        cells = dash.locator("section.card:has(h2:has-text('Granted')) tbody tr td:nth-child(2)").all_inner_texts()
        assert cells and all(c.strip() == "—" for c in cells), cells
        assert errors == [], errors
        dash.evaluate("() => refresh()")
        dash.wait_for_function("() => data.findings && data.findings.ok[0].member_count !== undefined")

    def test_typing_filters_every_section_and_says_so(self, dash):
        """The same box the Groups and Users tabs have: group, role, namespace or binding name."""
        self._open(dash)
        before = dash.locator("tbody tr").count()
        # The denominator is the sections SHOWN under the current filter — Built-in is hidden on
        # the default view, so its rows are not counted (Codex, #48).
        shown = dash.evaluate("() => ['ok','dangling','unresolved','unmanaged']"
                              ".reduce((n, t) => n + (data.findings[t] || []).length, 0)")
        assert shown == before
        dash.fill("#f-binding-search", "klta")
        dash.wait_for_function("() => view.bindingSearch === 'klta'")
        names = dash.locator("tbody tr td:first-child").all_inner_texts()
        assert names == ["app-ocp-rbac-klta-ns-audit"], names
        note = dash.locator("#binding-search-note").inner_text()
        assert "klta" in note and f"1 of {shown} bindings in the sections shown match" in note, note
        # The header counts the cluster, never the match.
        assert "Group bindings on this cluster" in dash.locator("#main").inner_text()
        dash.fill("#f-binding-search", "prod-ns admin")
        dash.wait_for_function("() => view.bindingSearch === 'prod-ns admin'")
        names = dash.locator("tbody tr td:first-child").all_inner_texts()
        assert names and all(n in ("was-managed", "app-ocp-rbac-alpha-ns-admin") for n in names), names
        dash.locator("#f-binding-search").press("Escape")
        dash.wait_for_function("() => view.bindingSearch === ''")
        assert dash.locator("tbody tr").count() == before

    def test_a_truncated_page_says_so_and_the_search_note_stops_promising_everything(self, dash):
        """The page holds FINDINGS_PAGE rows; the header counts the cluster. Without a disclosure a
        reader searching for a group past the cut concludes it holds no grant (Cursor, #48)."""
        self._open(dash)
        assert dash.locator("#binding-truncation-note").count() == 0, "the fixture fits in one page"
        dash.evaluate("() => { data.findings = Object.assign({}, data.findings, { truncated: true, total: 900 }); render(); }")
        note = dash.locator("#binding-truncation-note").inner_text()
        assert "of 900 group bindings" in note and "past the cut cannot be found here" in note, note
        dash.fill("#f-binding-search", "klta")
        dash.wait_for_function("() => view.bindingSearch === 'klta'")
        search = dash.locator("#binding-search-note").inner_text()
        assert "loaded bindings" in search and "past the cut is not searched" in search, search
        assert "see all of them" not in search
        dash.locator("#f-binding-search").press("Escape")
        dash.wait_for_function("() => view.bindingSearch === ''")
        dash.evaluate("() => refresh()")
        dash.wait_for_function("() => data.findings && data.findings.truncated === false")

    def test_a_cluster_switch_clears_the_search_and_keeps_the_sort(self, dash):
        self._open(dash)
        dash.fill("#f-binding-search", "klta")
        dash.wait_for_function("() => view.bindingSearch === 'klta'")
        dash.evaluate("() => { view.bindingSort = 'binding'; view.bindingDir = 'desc'; }")
        dash.evaluate("() => { navigate({ cluster: 'prod-east', groupsync: null, group: null, user: null }); }")
        assert dash.evaluate("() => view.bindingSearch") == ""
        assert dash.evaluate("() => [view.bindingSort, view.bindingDir]") == ["binding", "desc"]
        dash.evaluate("() => { navigate({ cluster: 'crc-local', groupsync: null, group: null, user: null });"
                      " view.bindingSort = 'group'; view.bindingDir = 'asc'; refresh(); }")
        dash.wait_for_selector("text=grant nobody")

    def test_column_headers_sort_and_reaches_puts_the_unknowns_last(self, dash):
        self._open(dash)
        dash.select_option("#f-binding", "all")
        dash.wait_for_function("() => document.body.innerText.includes('Built-in')")
        dash.locator("[data-sort-group='bind'][data-sort-key='reaches']").first.click()
        dash.wait_for_function("() => view.bindingSort === 'reaches' && view.bindingDir === 'desc'")
        cells = dash.locator("section.card:has(h2:has-text('Built-in')) tbody tr td:nth-child(2)").all_inner_texts()
        assert all(c.strip() == "—" for c in cells), cells
        # Sorting by binding name, ascending, on the Granted section.
        dash.locator("section.card:has(h2:has-text('Granted')) [data-sort-key='binding']").click()
        dash.wait_for_function("() => view.bindingSort === 'binding'")
        dash.locator("section.card:has(h2:has-text('Granted')) [data-sort-key='binding']").click()
        dash.wait_for_function("() => view.bindingSort === 'binding' && view.bindingDir === 'asc'")
        th = dash.locator("section.card:has(h2:has-text('Granted')) th[aria-sort='ascending']")
        assert th.count() == 1 and "binding" in th.inner_text().lower()   # CSS uppercases headers
        dash.evaluate("() => { view.bindingSort = 'group'; view.bindingDir = 'asc'; }")
        dash.select_option("#f-binding", "review")
        dash.wait_for_selector("text=grant nobody")

    def test_dangling_and_unresolved_are_both_shown(self, dash):
        self._open(dash)
        body = dash.locator("body").inner_text()
        assert "was-managed" in body, "the dangling binding must be listed"
        assert "app-ocp-rbac-klta-ns-audit" in body, "the unresolved binding must be listed"

    def test_the_headline_counts_only_actionable_findings(self, dash):
        """Built-in groups must not inflate the number — 145 of 154 on the real cluster."""
        self._open(dash)
        assert dash.locator(".hero .value").inner_text().strip() == "2"

    def test_builtin_is_not_on_the_default_view(self, dash):
        """Built-in groups are 145 of 154 on the real cluster. Listing them beside the
        findings would bury the signal, so the default view excludes them."""
        self._open(dash)
        body = dash.locator("body").inner_text()
        assert "system:serviceaccounts:ns0" not in body

    def test_builtin_is_reachable_through_the_filter(self, dash):
        """Excluded from the default view, not hidden — the tab claims to be about
        bindings, so every binding must be reachable from it."""
        self._open(dash)
        dash.select_option("#f-binding", "built_in")
        dash.wait_for_function(
            "() => document.body.innerText.includes('system:serviceaccounts:ns0')")

    def test_healthy_bindings_are_reachable_too(self, dash):
        """The original tab showed only non-resolving rows under a "Bindings" label,
        presenting 228 bindings as 154. Every one must be reachable."""
        self._open(dash)
        assert "Group bindings on this cluster" in dash.locator("body").inner_text()
        dash.select_option("#f-binding", "all")
        dash.wait_for_function(
            "() => document.body.innerText.includes('Granted')")

    def test_the_namespace_and_role_are_named(self, dash):
        """"Grants admin in prod-ns" is the actionable form; a group name alone is not."""
        self._open(dash)
        body = dash.locator("body").inner_text()
        assert "prod-ns" in body and "admin" in body

    def test_group_names_drill_through(self, dash):
        self._open(dash)
        assert dash.locator(".drill[data-group='was-managed']").count() == 1

    def test_a_row_with_no_tier_from_an_older_server_is_not_a_link_either(self, dash):
        """The drill rule is positive — ok, unmanaged, dangling — so a row that says nothing about
        whether a Group object exists cannot drill into a 404 (Codex second pass)."""
        self._open(dash)
        dash.evaluate("""() => {
            const strip = (rows) => rows.map(({ finding, ...rest }) => rest);
            const d = data.findings;
            data.findings = Object.assign({}, d, { ok: strip(d.ok), unresolved: strip(d.unresolved) });
            render();
        }""")
        assert dash.locator("section.card:has(h2:has-text('Granted')) .drill").count() == 0
        assert dash.locator("section.card:has(h2:has-text('Unresolved')) .drill").count() == 0
        dash.evaluate("() => refresh()")
        dash.wait_for_selector("section.card:has(h2:has-text('Granted')) .drill")

    def test_a_name_with_no_group_object_is_not_a_link_to_a_404(self, dash):
        """Built-in virtual groups never have a Group object and unresolved bindings name groups
        that never existed, so a drill from either could only reach the 404 card — which blamed a
        deletion that never happened (operator, 2026-09-04). Dangling keeps the drill: history."""
        self._open(dash)
        unresolved = dash.locator("section.card:has(h2:has-text('Unresolved')) tbody tr td:first-child")
        assert unresolved.count() >= 1
        assert unresolved.locator(".drill").count() == 0
        assert "app-ocp-rbac-klta-ns-audit" in unresolved.first.inner_text()
        assert dash.locator("section.card:has(h2:has-text('Dangling')) .drill[data-group='was-managed']").count() == 1
        dash.select_option("#f-binding", "built_in")
        dash.wait_for_function("() => document.body.innerText.includes('system:serviceaccounts:ns0')")
        assert dash.locator("section.card:has(h2:has-text('Built-in')) tbody tr").count() >= 1
        assert dash.locator("section.card:has(h2:has-text('Built-in')) .drill").count() == 0
        dash.select_option("#f-binding", "review")
        dash.wait_for_selector("text=grant nobody")

    def test_cluster_card_surfaces_the_count_without_navigating(self, dash):
        """Discoverability: the landing page must show that there is something to look at,
        or the page may as well not exist."""
        body = dash.locator("body").inner_text()
        assert "Bindings to review" in body


class TestTheShellAtPhoneWidth:
    """#166, measured on the live cluster before the fix: at 375 px the nine-tab bar was 676 px wide,
    `document.documentElement.scrollWidth` 696, and five tabs sat past the edge of a bar that could
    not scroll — unreachable. The shell owns the bar (#152), so the check runs on every tab."""
    TABS = ["home", "overview", "kpi", "groups", "users", "bindings", "policy", "nsaudit", "logins", "usage"]

    @pytest.mark.parametrize("tab", TABS)
    def test_no_horizontal_overflow_and_every_tab_inside_the_viewport(self, dash, tab):
        dash.set_viewport_size({"width": 375, "height": 740})
        dash.click(f"#tab-{tab}")
        dash.wait_for_function("() => document.querySelector('#main .card, #main section, #main .empty-note')")
        dash.wait_for_timeout(300)
        width = dash.evaluate("() => [document.documentElement.scrollWidth, innerWidth]")
        assert width[0] <= width[1], f"{tab}: the page scrolls sideways ({width[0]} > {width[1]})"
        beyond = dash.evaluate(
            "() => [...document.querySelectorAll('button.tab')].filter(t => t.getBoundingClientRect().right > innerWidth).map(t => t.id)")
        assert beyond == [], f"{tab}: tabs past the right edge: {beyond}"

    def test_phone_header_stays_compact_and_prefs_stay_labelled_on_screen(self, dash):
        """223 px at 375 (was 113): the two inline labels cost a row each. Below 520 px a label sits ABOVE its
        select, the pair shares one row with Refresh, and the labels stay on screen — not only in the
        accessibility tree: a select reading "Auto" or "Default" names nothing on its own (OB1, review 2 of
        #179; 167 px measured with the labels visible, 143 with them clipped)."""
        dash.set_viewport_size({"width": 375, "height": 740})
        got = dash.evaluate("""() => { const r = (e) => e.getBoundingClientRect();
            const head = document.querySelector('header.top'), mode = document.getElementById('pref-mode'), pal = document.getElementById('pref-palette');
            const lab = (s) => { const l = s.labels[0], b = r(l); return {name: l.textContent.trim(), visible: b.width > 1 && b.height > 1, above: b.bottom <= r(s).top}; };
            return {height: r(head).height, scrollWidth: document.documentElement.scrollWidth, mode: lab(mode), pal: lab(pal),
                    oneRow: Math.abs(r(mode).top - r(pal).top) < 1}; }""")
        assert got["height"] <= 180, got
        assert got["scrollWidth"] <= 375, got
        assert got["mode"] == {"name": "Appearance", "visible": True, "above": True}, got
        assert got["pal"] == {"name": "Colours", "visible": True, "above": True}, got
        assert got["oneRow"], got
        dash.select_option("#pref-mode", "dark")
        dash.select_option("#pref-palette", "trit")
        assert dash.evaluate("() => [document.documentElement.dataset.theme, document.documentElement.dataset.palette]") == ["dark", "trit"]



class TestAppearanceAndColours:
    """#152: appearance and palette are global shell state on <html>. The URL wins over the stored
    choice so a shared link opens as the sender saw it; the head script applies both before the
    stylesheet paints; the controls live in the static header, so the 60 s filter repaint cannot
    destroy them; a change is never a navigation, so Back keeps working."""

    def test_the_url_is_applied_before_the_first_paint_and_the_controls_mirror_it(self, page, server):
        page.goto(f"{server}/?mode=dark&theme=deuter#page=groups&cluster=crc-local")
        # Read at document-start, before the app's own script has run anything.
        assert page.evaluate("() => [document.documentElement.getAttribute('data-theme'), document.documentElement.getAttribute('data-palette')]") == ["dark", "deuter"]
        page.wait_for_selector("#pref-mode")
        assert page.evaluate("() => [document.getElementById('pref-mode').value, document.getElementById('pref-palette').value]") == ["dark", "deuter"]

    def test_junk_in_the_url_stamps_nothing(self, page, server):
        page.goto(f"{server}/?mode=purple&theme=%3Cscript%3E#page=groups&cluster=crc-local")
        page.wait_for_selector("#pref-mode")
        assert page.evaluate("() => [document.documentElement.hasAttribute('data-theme'), document.documentElement.hasAttribute('data-palette')]") == [False, False]

    def test_junk_in_the_url_does_not_discard_the_stored_choice(self, page, server):
        """Grok, review of #179 (D5): a junk value in the URL is not a choice; the reader's stored one stands."""
        page.goto(f"{server}/#page=groups&cluster=crc-local")
        page.wait_for_selector("#pref-mode")
        page.select_option("#pref-mode", "dark")
        page.goto(f"{server}/?mode=purple#page=groups&cluster=crc-local")
        page.wait_for_selector("#pref-mode")
        assert page.evaluate("() => [document.documentElement.getAttribute('data-theme'), document.getElementById('pref-mode').value]") == ["dark", "dark"]

    def test_a_change_survives_the_filter_repaint_a_navigation_and_a_reload(self, dash):
        dash.select_option("#pref-mode", "dark")
        dash.select_option("#pref-palette", "trit")
        before = dash.evaluate("() => history.state")
        dash.evaluate("() => renderFilters()")          # the 60 s repaint
        dash.click("#tab-users")
        dash.wait_for_selector("#tab-users[aria-current='page']")
        got = dash.evaluate("() => [document.documentElement.dataset.theme, document.documentElement.dataset.palette, location.search, document.getElementById('pref-mode').value]")
        assert got == ["dark", "trit", "?mode=dark&theme=trit", "dark"]
        assert before is not None and dash.evaluate("() => history.state && history.state.pos && history.state.pos.page") == "users", "the router's state was not preserved across the change"
        dash.goto(dash.url.split("?")[0] + "#page=groups&cluster=crc-local")  # no query: the stored choice must win
        dash.wait_for_selector("#pref-mode")
        assert dash.evaluate("() => [document.documentElement.dataset.theme, document.documentElement.dataset.palette]") == ["dark", "trit"]
        dash.select_option("#pref-mode", "")
        dash.select_option("#pref-palette", "")
        assert dash.evaluate("() => [document.documentElement.hasAttribute('data-theme'), localStorage.getItem('gsd-mode'), location.search]") == [False, None, ""]

    def test_accent_soft_follows_the_page_accent(self, dash):
        """Grok, review of #179 (F1): --accent-soft must be computed where --accent is overridden
        (body), not on :root — an unregistered custom property inherits its COMPUTED value, so a
        :root color-mix(var(--accent)) freezes against --tab-overview and the pressed chip on Users
        wears the wrong section's wash. Fails on the :root definition; passes with it on body."""
        def sample(tab):
            dash.click(f"#tab-{tab}")
            dash.wait_for_selector(f"#tab-{tab}[aria-current='page']")
            return dash.evaluate("""() => {
                const probe = document.createElement('div'); document.body.appendChild(probe);
                probe.style.background = 'var(--accent-soft)';
                const soft = getComputedStyle(probe).backgroundColor;
                probe.style.background = 'color-mix(in srgb, var(--accent) 14%, transparent)';
                const direct = getComputedStyle(probe).backgroundColor;
                const accent = getComputedStyle(document.body).getPropertyValue('--accent').trim();
                probe.remove(); return {soft, direct, accent}; }""")
        overview, users = sample("overview"), sample("users")
        assert users["accent"] != overview["accent"], "the two tabs share --accent — nothing to follow"
        assert users["soft"] == users["direct"], f"Users --accent-soft {users['soft']} froze on :root (page mix {users['direct']})"
        assert overview["soft"] == overview["direct"]
        assert users["soft"] != overview["soft"], "both tabs resolved to the same wash"

    def test_print_is_light_whatever_the_screen_theme(self, page, server):
        """OB1, review of #179: a print is paper — Chrome paints no page background by default, so the
        dark tokens put near-white text on white. The dark blocks are screen-only; the palette stays,
        in its light form. Fails on the ungated sheet (white text, dark scheme); passes gated."""
        page.goto(f"{server}/?mode=dark&theme=contrast#page=overview&cluster=crc-local")
        page.wait_for_selector(".hero .value")
        page.emulate_media(media="print")
        got = page.evaluate("() => { const cs = getComputedStyle(document.body); return [cs.color, cs.colorScheme, getComputedStyle(document.documentElement).getPropertyValue('--status-good').trim()]; }")
        assert got == ["rgb(11, 11, 11)", "light", "#076607"], got
        page.emulate_media(media="screen")
        assert page.evaluate("() => getComputedStyle(document.body).colorScheme") == "dark"

    def test_the_url_keeps_the_choice_across_back(self, dash):
        """OB1, review of #179: replaceState rewrote only the current entry, so Back restored an
        address without ?mode — and every entry pushed from there inherited the loss."""
        dash.click("#tab-groups")
        dash.wait_for_selector("tr[data-group]")
        dash.click("tr[data-group='app-ocp-rbac-alpha-ns-admin']")
        dash.wait_for_selector("#back-groups")
        dash.select_option("#pref-mode", "dark")
        dash.click("#back-groups")
        dash.wait_for_function("() => !document.querySelector('#back-groups')")
        assert dash.evaluate("() => [location.search, document.documentElement.dataset.theme, history.state.pos.page]") == ["?mode=dark", "dark", "groups"]

    def test_a_hashless_mode_link_keeps_the_query_after_boot(self, page, server):
        """Grok, review 2 of #179: boot used `location.hash || location.pathname`, which dropped ?mode
        from a hashless link — the sender believed the address bar still said dark."""
        page.goto(f"{server}/?mode=dark")
        page.wait_for_selector("#pref-mode")
        assert page.evaluate("() => [location.search, document.documentElement.getAttribute('data-theme'), document.getElementById('pref-mode').value]") == ["?mode=dark", "dark", "dark"]
        page.click("#tab-users")
        page.wait_for_selector("#tab-users[aria-current='page']")
        assert page.evaluate("() => location.search") == "?mode=dark"

    def test_a_valid_url_mode_wins_over_the_stored_choice(self, page, server):
        page.goto(f"{server}/#page=groups&cluster=crc-local")
        page.wait_for_selector("#pref-mode")
        page.select_option("#pref-mode", "dark")
        page.goto(f"{server}/?mode=light#page=groups&cluster=crc-local")
        page.wait_for_selector("#pref-mode")
        assert page.evaluate("() => [document.documentElement.getAttribute('data-theme'), document.getElementById('pref-mode').value]") == ["light", "light"]

    def test_the_controls_are_in_the_static_header_not_the_filter_bar(self, dash):
        assert dash.evaluate("() => document.querySelector('header.top #pref-mode') !== null && document.querySelector('#filters #pref-mode') === null")


class TestKpiPage:
    """#157 — the KPI page, to docs/design/overview-kpi-mock.html: both pods' self-report, the
    access-posture band, the four trends, the clusters table and the doors out, every number from
    /api/kpi (#156). The harness runs on a laptop with no cgroup, so the dashboard's block carries
    the disk and its own bytes and says the cgroup is unavailable — never 0."""

    def _open(self, dash):
        dash.click("#tab-kpi")
        dash.wait_for_selector(".kpi-page .kband .kpi", timeout=10_000)
        return dash

    def test_the_five_sections_render_from_the_payload(self, dash):
        self._open(dash)
        headings = [h.split("\n")[0].strip() for h in dash.locator("section.kpi-page > h2").all_inner_texts()]
        assert headings[:4] == ["System status", "Access posture", "Trends", "Clusters"]
        assert dash.locator(".kpi-page .kband .kpi").count() == 6
        assert dash.locator(".kpi-page .trend").count() == 4
        assert dash.locator(".kpi-page .comp").count() == 2
        assert dash.locator(".kpi-page .kdoor").count() == 1
        # The band's figures are the clusters' sums: groups from /api/kpi's posture, not invented.
        groups = int(dash.locator('.kpi-page .kpi[data-kpi="groups"] .value').inner_text().replace(",", ""))
        rows = dash.locator(".kpi-page tbody tr")
        assert rows.count() == 2
        per_cluster = [int(rows.nth(i).locator("td").nth(2).inner_text().replace(",", "")) for i in range(rows.count())]
        assert groups == sum(per_cluster)

    def test_the_cluster_selector_is_hidden_and_the_page_is_fleet_wide(self, dash):
        self._open(dash)
        assert dash.locator("#f-cluster").count() == 0
        assert dash.locator("#scope-note").inner_text().strip() == ""

    def test_status_is_never_colour_alone_and_the_mark_sits_at_the_threshold(self, dash):
        self._open(dash)
        # every state carries a word and a glyph (the .badge convention)
        for i in range(dash.locator(".kpi-page .badge").count()):
            b = dash.locator(".kpi-page .badge").nth(i)
            assert b.inner_text().strip() and b.locator(".glyph").count() == 1
        # the amber mark is drawn where the configured threshold says, on every measured track
        marks = dash.evaluate("""() => [...document.querySelectorAll('.kpi-page .track')].map(t => ({
            th: t.dataset.th, prop: getComputedStyle(t).getPropertyValue('--th').trim(),
            label: t.getAttribute('aria-label')}))""")
        assert marks, "no meter rendered"
        for m in marks:
            assert m["prop"] == f"{m['th']}%", m
            assert m["label"], m
        # the rule line names the thresholds it applied
        rule = dash.locator(".kpi-page .comp .rule").first.inner_text()
        assert ">80% memory" in rule and ">1% throttled periods" in rule

    def test_no_cgroup_reads_as_unavailable_not_zero(self, dash):
        self._open(dash)
        dashboard = dash.locator('.kpi-page .comp[data-comp="dashboard"]')
        # a laptop has no cgroup v2: the memory and CPU meters are unmeasured, the disk is measured
        vals = dashboard.locator(".meter-val").all_inner_texts()
        assert vals[0] == "unavailable" and vals[1] == "unavailable" and vals[2] == "unavailable"
        assert "node disk" in vals[3]
        assert "unmeasured, not zero" in dashboard.locator(".sub").first.inner_text()
        # the report service has not reported: unavailable, in words
        report = dash.locator('.kpi-page .comp[data-comp="report"]')
        assert "unavailable" in report.locator(".badge").inner_text()

    def test_trends_state_the_retention_edge_and_the_report_timeline(self, dash):
        self._open(dash)
        retains = dash.locator(".kpi-page .trend .retain").all_inner_texts()
        assert any("history retained since" in r for r in retains)
        assert any("timeline starts" in r or "no report run recorded yet" in r for r in retains)
        assert dash.locator(".kpi-page .spark").count() == 4

    def test_the_doors_render_only_when_configured(self, dash):
        self._open(dash)
        # the fixture configures neither Grafana nor the console: prose, no dead buttons
        assert dash.locator(".kpi-page .kdoor .btn").count() == 0
        assert "grafana.url" in dash.locator(".kpi-page .kdoor p").inner_text()

    def test_a_cluster_row_opens_its_overview(self, dash):
        self._open(dash)
        dash.locator(".kpi-page tbody tr").first.click()
        dash.wait_for_function("() => location.hash.includes('page=overview') && location.hash.includes('cluster=crc-local')")

    def test_holds_at_phone_width_with_the_table_scrolling_in_its_own_container(self, dash):
        dash.set_viewport_size({"width": 375, "height": 740})
        self._open(dash)
        dash.wait_for_timeout(300)
        width = dash.evaluate("() => [document.documentElement.scrollWidth, innerWidth]")
        assert width[0] <= width[1], f"the page scrolls sideways ({width[0]} > {width[1]})"
        table = dash.evaluate("() => { const s = document.querySelector('.kpi-page .scroll-x'); return [s.scrollWidth, s.clientWidth]; }")
        assert table[0] > table[1], "the clusters table must scroll inside its own container, not clip"

    def test_a_shared_day_across_clusters_is_one_summed_point(self, dash):
        """Review of #157 (Grok, P6): the sparkline concatenated the clusters' per-day rows and the
        Map kept the last cluster's — a day both clusters had rows for read as one cluster's figure
        while the tile summed both. The buckets are summed per day before the polyline is drawn."""
        self._open(dash)
        points = dash.evaluate("""() => {
          const day = new Date().toISOString().slice(0, 10);
          const k = data.kpi;
          for (const c of Object.keys(k.trends)) k.trends[c].activity.reports = [{ day, runs: c === 'crc-local' ? 2 : 3 }];
          document.getElementById('main').innerHTML = kpiPage();
          const svg = document.querySelectorAll('.kpi-page .spark')[3];
          return svg.getAttribute('aria-label');
        }""")
        assert points.endswith("5 over the last seven days"), points

    # A cgroup sample with the mock's own figures (docs/design/overview-kpi-mock.html): 19.3 % of 512Mi,
    # 1.10 % throttled over a 1 % mark, the node disk 83 % full.
    MOCK_SAMPLE = """() => { data.kpi.system.dashboard = {as_of: data.kpi.as_of,
        memory: {used_bytes: 103600000, limit_bytes: 536870912},
        cpu: {limit_cores: 0.5, usage_seconds: 100, periods: 20853, throttled_periods: 230, throttled_seconds: 8.71,
              cores_used: 0.004, throttled_fraction: 0.011, rate_interval_seconds: 60},
        disk: {used_bytes: 50e9, total_bytes: 60e9}, data: {db_bytes: 1, wal_bytes: 0, backups: {count: 0, bytes: 0}}};
      render(); }"""

    def test_the_throttled_track_is_scaled_so_position_reads(self, dash):
        """The mock draws the 1 % throttle mark at 20 % of its track (a track to 5 %). On a 0–100 % track the
        mark sat 3 px from the left edge and the mock's 1.10 % (watch) and 0.05 % (healthy) filled within half a
        pixel of each other (measured at 1280 px) — the position the rule line promises read nothing."""
        self._open(dash)
        dash.evaluate(self.MOCK_SAMPLE)
        rows = dash.evaluate("""() => [...document.querySelectorAll('.comp[data-comp="dashboard"] .meter-row')].map(m => ({
            label: m.querySelector('.meter-lab').innerText, th: m.querySelector('.track').dataset.th,
            width: +m.querySelector('.fill').dataset.width, warn: m.querySelector('.fill').classList.contains('warn'),
            aria: m.querySelector('.track').getAttribute('aria-label')}))""")
        by = {r["label"]: r for r in rows}
        assert by["MEMORY"]["th"] == "80" and abs(by["MEMORY"]["width"] - 19.3) < 0.1 and not by["MEMORY"]["warn"]
        assert by["THROTTLED"]["th"] == "20" and abs(by["THROTTLED"]["width"] - 22.0) < 0.1 and by["THROTTLED"]["warn"], by["THROTTLED"]
        assert by["THROTTLED"]["aria"] == "Throttled: 1.1% of the limit, amber above 1% on a track to 5%", by["THROTTLED"]["aria"]
        assert "watch" in dash.locator('.comp[data-comp="dashboard"] .badge').inner_text()

    def test_the_fill_the_badge_and_the_rule_come_from_one_decision(self, dash):
        """A threshold the payload does not carry must not split the decision: the fill's class, the badge word
        and the rule line are one comparison per meter, so they agree whatever the input. With two comparisons
        the badge said watch (50 > null is true in JavaScript) over a green fill."""
        self._open(dash)
        agree = dash.evaluate("""() => { data.kpi.system.dashboard = {as_of: data.kpi.as_of, memory: {used_bytes: 100, limit_bytes: 200},
            data: {db_bytes: 1, wal_bytes: 0, backups: {count: 0, bytes: 0}}};
          data.kpi.thresholds = Object.assign({}, data.kpi.thresholds, {memory_percent: null}); render();
          const c = document.querySelector('.comp[data-comp="dashboard"]');
          return {badge: c.querySelector('.badge').innerText.trim(), warnFills: c.querySelectorAll('.fill.warn').length,
                  rule: c.querySelector('.rule').innerText.startsWith('Watch:')}; }""")
        assert (agree["badge"] == "watch") == (agree["warnFills"] > 0) == agree["rule"], agree

    def test_an_over_threshold_fill_clears_graphical_contrast_on_its_track(self, dash):
        """1.4.11: the fill's extent against the track's wash IS the meter, so the two composited colours —
        not the tokens — must be 3:1 apart. The badge amber measured 2.70:1 on --page-2 in light."""
        self._open(dash)
        dash.evaluate(self.MOCK_SAMPLE)
        pair = dash.evaluate("""() => { const fill = document.querySelector('.comp[data-comp="dashboard"] .fill.warn');
            return [getComputedStyle(fill).backgroundColor, getComputedStyle(fill.parentElement).backgroundColor]; }""")

        def luminance(css):
            r, g, b = (int(v) for v in css[css.index("(") + 1:css.index(")")].split(",")[:3])
            lin = lambda c: (c / 255) / 12.92 if c / 255 <= 0.04045 else (((c / 255) + 0.055) / 1.055) ** 2.4  # noqa: E731
            return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)

        hi, lo = sorted((luminance(pair[0]), luminance(pair[1])), reverse=True)
        assert (hi + 0.05) / (lo + 0.05) >= 3.0, pair

    def test_the_sparkline_ends_on_the_payloads_as_of_day(self, dash):
        """The buckets are the server's UTC days, so the line's day list comes from the payload's as-of, not the
        browser's clock: a reader on the other side of midnight UTC sees the thirty days the server bucketed."""
        self._open(dash)
        aria = dash.evaluate("""() => { const day = new Date(Date.now() - 3 * 86400000).toISOString().slice(0, 10);
            data.kpi.as_of = day + 'T12:00:00Z';
            data.kpi.trends['crc-local'].activity.membership = [{day, added: 4, removed: 0}];
            render(); return document.querySelector('.trend svg').getAttribute('aria-label'); }""")
        assert aria.endswith("0, 0, 0, 0, 0, 0, 4 over the last seven days"), aria

    def test_the_bindings_tile_counts_every_tier_the_access_tab_counts(self, dash, server):
        """The seed's cluster holds ten group bindings: one ok, one dangling, one unresolved, one unmanaged (hand-made
        on a synced group), six built-in. The tile's figure plus its built-in note is the Access granted tab's
        headline; a posture that dropped the unmanaged tier read 3 + 6 for a cluster with 10."""
        self._open(dash)
        total = httpx.get(f"{server}/api/clusters/crc-local/bindings/findings").json()["total"]
        value = int(dash.locator('.kpi-page .kpi[data-kpi="bindings"] .value').inner_text().replace(",", ""))
        note = dash.locator('.kpi-page .kpi[data-kpi="bindings"] .note').inner_text()
        builtin = int(note.split("+")[1].split(" ")[0].replace(",", ""))
        assert (value, builtin, total) == (4, 6, 10)

    def test_the_kpi_page_follows_the_hosts_headline_not_the_selected_remote(self, page, scoped_server):
        """The KPI page is fleet-wide and /api/kpi is gated on the host's tier, like the report ticket. Read per
        SELECTED cluster, a host administrator with a self-only remote selected was refused the payload the server
        had just served, and a self reader with a wide remote selected got Loading… for a fetch the guard in
        refresh() never makes. Both guards read the host's headline."""
        p = _open_as(page, scoped_server, "root")
        p.evaluate("""() => {
          data.whoami.visibility.clusters = Object.assign({}, data.whoami.visibility.clusters,
            { east: { policy: "self-only", identity: "none", scope: "self" } });
          data.clusters = (data.clusters || []).concat([{ id: "east", visibility: { policy: "self-only", scope: "self" } }]);
          view.cluster = "east"; view.page = "kpi"; render();
        }""")
        assert p.evaluate("() => narrowedReader()") is True, "the selected remote is narrowed for root"
        assert p.evaluate("() => narrowedOnHost()") is False, "root is wide on the host"
        assert p.locator("#main .scope-refusal").count() == 0, "a host administrator must not be refused the fleet page over the selected remote"
        p.evaluate("""() => {
          data.whoami.visibility.scope = "self";
          data.whoami.visibility.clusters = Object.assign({}, data.whoami.visibility.clusters,
            { west: { policy: "remote-sar", identity: "same-as-host", scope: "all" } });
          data.clusters = (data.clusters || []).concat([{ id: "west", visibility: { policy: "remote-sar", scope: "all" } }]);
          view.cluster = "west"; data.kpi = null; render();
        }""")
        assert p.locator("#main .scope-refusal").count() == 1, "narrowed on the host is refused, not left on Loading…"
        # a designed 403 that reaches the renderer is the same card, never an exception
        p.evaluate("() => { data.whoami.visibility.scope = 'all'; view.cluster = null; data.kpi = {forbidden: true}; render(); }")
        assert p.locator("#main .scope-refusal").count() == 1


    def test_reduced_motion_stops_the_heartbeat(self, dash):
        self._open(dash)
        dash.emulate_media(reduced_motion="reduce")
        assert dash.evaluate("() => getComputedStyle(document.querySelector('.kpi-page .beat')).animationName") == "none"
        dash.emulate_media(reduced_motion="no-preference")
        assert dash.evaluate("() => getComputedStyle(document.querySelector('.kpi-page .beat')).animationName") == "kpi-beat"


class TestNamespaces:
    """#167: namespaces are entities, not a filter. The audit tab lists every namespace the poller sees
    (nine in the seed, two of them labelled twice, one with no grant at all), a pattern box finds them
    by name OR label value with the AND contract the other boxes honour, and a row opens a page that is
    the third drill-down peer of a group and a user."""

    def _open(self, dash):
        dash.click('button.tab:text-is("Namespace audit")')
        dash.wait_for_selector("h2:text-is('Namespaces')")

    def test_every_namespace_is_listed_not_only_those_with_a_grant(self, dash):
        self._open(dash)
        assert dash.locator("tr[data-ns]").count() == 9
        head = dash.locator("h2", has_text="Namespaces").first.inner_text()
        assert "9" in head
        # the label columns come from the configured keys, by their short names
        # textContent, not inner_text: table headers are upper-cased by CSS
        heads = dash.locator("h2:text-is('Namespaces') ~ div th").evaluate_all("els => els.map(e => e.textContent.trim())")
        assert heads[:3] == ["Namespace", "mnemonic", "app-environment"]
        quiet = dash.locator("tr[data-ns='quiet-corner']").inner_text()
        assert "demo" in quiet and "qa" in quiet, "a namespace with no grant still shows its labels"

    def test_the_box_finds_by_name_or_label_and_ands_its_words(self, dash):
        self._open(dash)
        box = dash.locator("#f-ns-search")
        box.fill("demo")
        dash.wait_for_function("() => document.querySelectorAll('tr[data-ns]').length === 2")
        names = sorted(dash.locator("tr[data-ns]").evaluate_all("els => els.map(e => e.dataset.ns)"))
        assert names == ["prod-ns", "quiet-corner"], "demo is a label value, not a name"
        box.fill("demo qa")
        dash.wait_for_function("() => document.querySelectorAll('tr[data-ns]').length === 1")
        assert dash.locator("tr[data-ns]").first.get_attribute("data-ns") == "quiet-corner"
        box.fill("demo zzz")
        dash.wait_for_function("() => document.querySelectorAll('tr[data-ns]').length === 0")
        note = dash.locator("h2:text-is('Namespaces') ~ div.empty-note").inner_text()
        assert "the filter is hiding them" in note and "9" in note
        assert "0 of 9 shown" in dash.locator("h2", has_text="Namespaces").first.inner_text()
        box.press("Escape")
        dash.wait_for_function("() => document.querySelectorAll('tr[data-ns]').length === 9")

    def test_a_row_opens_the_namespace_and_back_returns_to_the_list(self, dash):
        self._open(dash)
        dash.locator("tr[data-ns='prod-ns'] button.drill").click()
        dash.wait_for_selector("#back")
        assert dash.evaluate("() => location.hash") == "#page=nsaudit&cluster=crc-local&ns=prod-ns"
        assert dash.locator("#back").inner_text().strip() == "← all namespaces"
        text = dash.locator("#main").text_content()
        for h in ("Who reaches it, and through which group", "Direct grants", "History", "Same mnemonic"):
            assert h in text, h
        assert "quiet-corner" in text, "the sibling under the mnemonic label"
        # the KPI row: the two labels, people, via groups, direct grants
        assert dash.locator(".kpi .label", has_text="People who reach it").count() == 1
        assert dash.locator("tr[data-group]").count() >= 1, "a group that grants it, drillable"
        dash.locator("#back").click()
        dash.wait_for_selector("h2:text-is('Namespaces')")
        assert dash.evaluate("() => location.hash") == "#page=nsaudit&cluster=crc-local"

    def test_the_group_drill_from_the_page_leaves_the_namespace_behind(self, dash):
        self._open(dash)
        dash.locator("tr[data-ns='prod-ns'] button.drill").click()
        dash.wait_for_selector("tr[data-group] button.drill")
        group = dash.locator("tr[data-group]").first.get_attribute("data-group")
        dash.locator("tr[data-group] button.drill").first.click()
        dash.wait_for_selector("#back-groups, #back")
        hash_ = dash.evaluate("() => location.hash")
        assert f"group={group}" in hash_ and "ns=" not in hash_, hash_
        assert dash.evaluate("() => view.page") == "groups"
        dash.go_back()
        dash.wait_for_selector("h2:text-is('Who reaches it, and through which group')")
        assert dash.evaluate("() => view.ns") == "prod-ns"

    def test_a_sibling_opens_its_own_page(self, dash):
        self._open(dash)
        dash.locator("tr[data-ns='prod-ns'] button.drill").click()
        dash.wait_for_selector("button.drill[data-ns='quiet-corner']")
        dash.locator("button.drill[data-ns='quiet-corner']").click()
        # wait for the NEW page: view.ns flips at once, the old page's #back stays until the refetch paints
        dash.wait_for_selector("h2:text-is('quiet-corner')")
        assert dash.locator("#back").inner_text().strip() == "← prod-ns"
        assert "No RoleBinding names a person here directly" in dash.locator("#main").inner_text()

    def test_the_page_holds_at_phone_width(self, dash):
        self._open(dash)
        dash.locator("tr[data-ns='prod-ns'] button.drill").click()
        dash.wait_for_selector("#back")
        dash.set_viewport_size({"width": 375, "height": 740})
        dash.wait_for_timeout(300)
        assert dash.evaluate("() => document.documentElement.scrollWidth <= innerWidth")

    # -- the review of #167 (Grok, pass 1 — docs/REVIEW_namespaces.md) ------------------------------

    def test_switching_cluster_abandons_the_namespace(self, dash):
        """The hole already closed for a group and a user: `ns` joined the position without joining the
        selector's drop list, so a namespace page survived a cluster switch and refetched the name
        against the new cluster — a different object, or a 404 (Grok F2)."""
        self._open(dash)
        dash.locator("tr[data-ns='prod-ns'] button.drill").click()
        dash.wait_for_selector("#back")
        dash.select_option("#f-cluster", "prod-east")
        dash.wait_for_function("() => view.cluster === 'prod-east' && !document.querySelector('#back')")
        assert "ns=" not in dash.evaluate("() => location.hash")
        assert dash.evaluate("() => view.ns") is None
        assert "Dashboard API error" not in dash.locator("#main").inner_text()

    def test_the_keyboard_user_drill_from_the_page_leaves_the_namespace_behind(self, dash):
        """Enter on a person's name is the keyboard twin of the click, which already dropped `ns` (Grok F2)."""
        self._open(dash)
        dash.locator("tr[data-ns='prod-ns'] button.drill").click()
        dash.wait_for_selector("tr[data-user] button.drill")
        dash.locator("tr[data-user] button.drill").first.focus()
        dash.keyboard.press("Enter")
        dash.wait_for_function("() => view.user")
        hash_ = dash.evaluate("() => location.hash")
        assert "user=" in hash_ and "ns=" not in hash_, hash_

    def test_the_page_offers_no_export_of_a_table_it_does_not_show(self, dash):
        """The audit tab exports its direct-grants table; the namespace page holds no table that descriptor
        owns, and the buttons there exported rows the reader was not looking at (Grok F5)."""
        self._open(dash)
        assert dash.locator("#export-csv").count() == 1
        dash.locator("tr[data-ns='prod-ns'] button.drill").click()
        dash.wait_for_selector("#back")
        assert dash.locator("#export-csv").count() == 0

    def test_a_person_named_cluster_wide_is_on_the_page(self, dash):
        """carol holds cluster-admin through a ClusterRoleBinding naming her (the seed's `carol-ca`): the
        list's envelope counted her once, and the page for a namespace nobody else reaches said nothing
        of her (Grok F4). Platform identities (kubeadmin's `ka`) stay off the line."""
        self._open(dash)
        dash.locator("tr[data-ns='quiet-corner'] button.drill").click()
        dash.wait_for_selector("h2:text-is('quiet-corner')")
        line = dash.locator("#main .filterbar-note", has_text="Also reached cluster-wide").inner_text()
        assert "carol" in line and "cluster-admin" in line and "named directly" in line, line
        assert "kubeadmin" not in line
        assert dash.locator("#main button.drill[data-user='carol']").count() == 1

    def test_the_namespaces_card_at_the_self_tier_speaks_of_the_viewers_grants(self, page, scoped_server):
        """`nobody` holds no membership and no grant: the card lists nothing, and its copy must say that is
        their view — not that the cluster has no namespaces, nor that it shows "every namespace the poller
        sees" (Grok F3, OB1 F3)."""
        p = _open_as(page, scoped_server, "nobody")
        p.locator("button[data-nav='nsaudit']").click()
        p.wait_for_selector("h2:text-is('Namespaces')")
        card = p.locator("h2:text-is('Namespaces')").locator("xpath=..").inner_text()
        assert "No namespaces recorded" not in card and "Every namespace the poller sees" not in card, card
        assert "your own memberships and grants" in card and "your view, not the cluster" in card, card

    def test_a_cluster_wide_path_of_the_viewers_own_lists_every_namespace(self, page, scoped_server):
        """The detail's reach rule opens every namespace for a viewer with a cluster-wide path; the list says the
        same (OB1 F2). carol's one grant is the ClusterRoleBinding naming her: nine rows, the line names the
        path as hers, the columns count her in-namespace paths (none). The fixture names no label keys, so
        there is no label column."""
        p = _open_as(page, scoped_server, "carol")
        p.locator("button[data-nav='nsaudit']").click()
        p.wait_for_selector("tr[data-ns]")
        heads = p.locator("h2:text-is('Namespaces') ~ div th").evaluate_all("els => els.map(e => e.textContent.trim())")
        assert heads == ["Namespace", "Via groups", "Direct grants"]
        assert p.locator("tr[data-ns]").count() == 9
        card = p.locator("h2:text-is('Namespaces')").locator("xpath=..").inner_text()
        assert "0 groups bound cluster-wide and 1 cluster-wide direct grant of yours reach every namespace below" in card, card
        assert p.locator("tr[data-ns] td.num").evaluate_all("els => els.every(e => e.textContent.trim() === '0')")

    def test_the_self_tier_page_carries_the_viewers_own_paths_only(self, page, scoped_server):
        """alice's group holds the hand-made cluster-admin ClusterRoleBinding: nine rows through it (OB1 F2), and
        prod-ns's page opens with her own memberships, no People KPI and no label KPI (no keys configured)."""
        p = _open_as(page, scoped_server, "alice")
        p.locator("button[data-nav='nsaudit']").click()
        p.wait_for_selector("tr[data-ns]")
        assert p.locator("tr[data-ns]").count() == 9
        assert "1 group bound cluster-wide and 0 cluster-wide direct grants of yours" in p.locator("#main").inner_text()
        p.locator("tr[data-ns='prod-ns'] button.drill").click()
        p.wait_for_selector("h2:text-is('prod-ns')")
        kpis = p.locator(".kpi .label").evaluate_all("els => els.map(e => e.textContent.trim())")
        # The self tier's labels say whose paths these are: an empty "Direct grants" on a page that holds
        # only the viewer's own is a number under someone else's label (OB3, integration review, C10).
        assert kpis == ["Via your groups", "Your direct grants"], kpis
        body = p.locator("#main").inner_text()
        assert "Your own memberships that reach this namespace" in body and "Also reached cluster-wide" in body

    def test_the_self_tier_page_never_speaks_for_everyone(self, page, scoped_server):
        """At the self tier `direct_grants` and `via_groups` are the viewer's OWN paths, so an empty list says
        nothing about anyone else: prod-ns carries jdoe's direct grant and klt-pass-both is bound to
        app-ocp-rbac-klta-ns-audit, and alice's pages read "No RoleBinding names a person here directly, which
        is the state an access review wants to confirm" and "not granted to anyone through the policy system"
        — false statements about the cluster, made to the reader least able to check them (OB3, integration
        review, C10). The labels follow the numbers beside them (SPEC_per_user_visibility: never a recomputed
        number under its old label)."""
        p = _open_as(page, scoped_server, "alice")
        p.goto(f"{scoped_server}/#page=nsaudit&cluster=crc-local&ns=prod-ns")
        p.wait_for_selector("h2:text-is('prod-ns')")
        body = p.locator("#main").inner_text()
        assert "names a person here directly" not in body, body
        assert "No binding names you here directly" in body, body
        kpis = p.locator(".kpi .label").evaluate_all("els => els.map(e => e.textContent.trim())")
        assert "Via your groups" in kpis and "Your direct grants" in kpis, kpis
        p.goto(f"{scoped_server}/#page=nsaudit&cluster=crc-local&ns=klt-pass-both")
        p.wait_for_selector("h2:text-is('klt-pass-both')")
        body = p.locator("#main").inner_text()
        assert "not granted to anyone" not in body and "No group-based binding names this namespace" not in body, body
        assert "None of your own memberships reaches this namespace" in body, body

    def test_a_platform_only_cluster_wide_path_explains_the_self_tier(self, page, scoped_server):
        """kubeadmin's one binding is the platform-identity ClusterRoleBinding `ka`: at the self tier it reaches
        every namespace (nine rows) and the line says why without claiming "0 grants reach every namespace"
        (Codex, pass 2)."""
        p = _open_as(page, scoped_server, "kubeadmin")
        p.locator("button[data-nav='nsaudit']").click()
        p.wait_for_selector("tr[data-ns]")
        assert p.locator("tr[data-ns]").count() == 9
        card = p.locator("h2:text-is('Namespaces')").locator("xpath=..").inner_text()
        assert "platform identity of yours reaches every namespace below" in card, card
        assert "0 cluster-wide direct grants of yours" not in card

    def test_history_distinguishes_baseline_added_and_removed(self, dash):
        """A baseline row is not an addition and must not wear the added colour (Grok P5, Codex B, pass 2);
        the seed holds only baseline rows, so the three shapes are painted from one payload."""
        self._open(dash)
        dash.locator("tr[data-ns='prod-ns'] button.drill").click()
        dash.wait_for_selector("h2:text-is('prod-ns')")
        dash.evaluate("""() => { data.ns.changes = [
            {change: "added", baseline: 1, subject_kind: "User", subject_name: "b", role_name: "view", binding_kind: "RoleBinding", binding_name: "b-rb", observed_at: "2026-09-18T00:00:00Z"},
            {change: "added", baseline: 0, subject_kind: "User", subject_name: "a", role_name: "view", binding_kind: "RoleBinding", binding_name: "a-rb", observed_at: "2026-09-18T00:01:00Z"},
            {change: "removed", baseline: 0, subject_kind: "User", subject_name: "r", role_name: "view", binding_kind: "RoleBinding", binding_name: "r-rb", observed_at: "2026-09-18T00:02:00Z"}];
            render(); }""")
        cells = dash.locator("td[class^='change-']").evaluate_all("els => els.map(e => [e.className, e.innerText.trim()])")
        assert cells == [["change-baseline", "first observed"], ["change-added", "+ granted"], ["change-removed", "− revoked"]], cells

    @pytest.mark.parametrize(("kind", "key"), [("user", "Enter"), ("user", "Space"), ("group", "Enter"), ("group", "Space")])
    def test_namespace_drills_work_from_the_keyboard(self, dash, kind, key):
        """Enter on a group's name went nowhere: the key handler cancelled the native click and navigated only
        for a person's name (Grok V1, Codex C, pass 2). Every drill takes the click's path now."""
        self._open(dash)
        dash.locator("tr[data-ns='prod-ns'] button.drill").click()
        dash.wait_for_selector("h2:text-is('prod-ns')")
        button = dash.locator(f"tr[data-{kind}] button.drill").first
        button.focus()
        button.press(key)
        dash.wait_for_function(f"() => !!view.{kind}")
        assert dash.evaluate("() => view.ns") is None
        assert "ns=" not in dash.evaluate("() => location.hash")
        dash.go_back()
        dash.wait_for_function("() => view.ns === 'prod-ns'")

    def test_virtual_groups_are_badged_in_the_table_and_folded_on_the_cluster_wide_line(self, dash):
        """Measured on CRC (the walk of #167's deployed head): demo-prod's cluster-wide line listed 54 bindings,
        41 of them to `system:` groups — access with no person behind it. Badged in the table, folded on the
        line, never dropped."""
        self._open(dash)
        dash.locator("tr[data-ns='prod-ns'] button.drill").click()
        dash.wait_for_selector("h2:text-is('prod-ns')")
        dash.evaluate("""() => {
          data.ns.via_groups = [...data.ns.via_groups, {group_name: "system:serviceaccounts:prod-ns", binding_kind: "RoleBinding", binding_name: "system:image-pullers",
                                 role_kind: "ClusterRole", role_name: "system:image-puller", managed_source: null, member_count: 0, is_platform: 1}];
          data.ns.cluster_wide_groups = [...data.ns.cluster_wide_groups,
            ...["system:authenticated", "system:nodes", "system:masters", "system:serviceaccounts"].map(g => ({group_name: g, binding_kind: "ClusterRoleBinding",
                 binding_name: g + "-crb", role_kind: "ClusterRole", role_name: "basic-user", managed_source: null, member_count: 0, is_platform: 1}))];
          render();
        }""")
        assert dash.locator("tr[data-group='system:serviceaccounts:prod-ns'] .badge", has_text="platform").count() == 1
        line = dash.locator("#main .filterbar-note", has_text="Also reached cluster-wide").inner_text()
        assert "4 platform bindings to 4 virtual groups (system:authenticated, system:masters, system:nodes, … 1 more)" in line, line
        assert "system:serviceaccounts-crb" not in line and line.count("system:") == 3, line

    def test_the_fold_says_how_many_virtual_groups_and_names_the_most_bound_first(self, dash):
        """CRC's demo-prod fold read "35 platform bindings to virtual groups (system:authenticated,
        system:cluster-admins, system:masters, …)": the three names were an accident of role order (basic-user,
        then cluster-admin) and the "…" hid how many groups the rest were. Most-bound first — `system:authenticated`,
        every logged-in user, carries most of a cluster's platform bindings — and the fold counts the groups
        (OB1, pass 3 of #167)."""
        self._open(dash)
        dash.locator("tr[data-ns='prod-ns'] button.drill").click()
        dash.wait_for_selector("h2:text-is('prod-ns')")
        dash.evaluate("""() => {
          data.ns.cluster_wide_groups = ["system:nodes", "system:serviceaccounts", "system:authenticated", "system:masters", "system:serviceaccounts"]
            .map((g, i) => ({group_name: g, binding_kind: "ClusterRoleBinding", binding_name: g + "-crb-" + i, role_kind: "ClusterRole",
                             role_name: "basic-user", managed_source: null, member_count: 0, is_platform: 1}));
          data.ns.cluster_wide_grants = [];
          render();
        }""")
        line = dash.locator("#main .filterbar-note", has_text="Also reached cluster-wide").inner_text()
        assert "every namespace: 5 platform bindings to 4 virtual groups (system:serviceaccounts, system:authenticated, system:masters, … 1 more) that every namespace carries." in line, line
        dash.evaluate("""() => { data.ns.cluster_wide_groups = data.ns.cluster_wide_groups.slice(2, 3); render(); }""")
        line = dash.locator("#main .filterbar-note", has_text="Also reached cluster-wide").inner_text()
        assert "by one binding that grants every namespace: 1 platform binding to 1 virtual group (system:authenticated) that every namespace carries." in line, line

    def test_a_virtual_groups_default_binding_is_not_badged_hand_made(self, dash):
        """`system:image-pullers` in every OpenShift namespace binds `system:serviceaccounts:<ns>`: the platform
        makes it, nobody hand-makes it, and the findings tier it `built_in`, never `unmanaged` — yet the who-reaches
        table put the `hand-made` badge beside the `platform` one (CRC's demo-prod page at b6c96905de; OB1, pass 3
        of #167). The seed's `pullers-0` is that binding; `was-managed-rb`, a real group's hand-made binding, keeps
        its badge."""
        self._open(dash)
        dash.locator("tr[data-ns='ns0'] button.drill").click()
        dash.wait_for_selector("h2:text-is('ns0')")
        row = dash.locator("tr[data-group='system:serviceaccounts:ns0']")
        assert row.locator(".badge", has_text="platform").count() == 1
        assert row.locator(".badge", has_text="hand-made").count() == 0, row.inner_text()
        dash.go_back()
        dash.wait_for_selector("tr[data-ns='prod-ns']")
        dash.locator("tr[data-ns='prod-ns'] button.drill").click()
        dash.wait_for_selector("h2:text-is('prod-ns')")
        assert dash.locator("tr[data-group='was-managed'] .badge", has_text="hand-made").count() == 1

    def test_the_via_groups_column_counts_groups_of_people_not_virtual_groups(self, dash):
        """On OpenShift every namespace carries `system:image-pullers` → `system:serviceaccounts:<ns>`, so a Via
        groups column that counts virtual groups reads 1 or more on every row and the card's "zero in both is a
        result" can never happen; the envelope's cluster-wide count already leaves them out (pass 2, D). The row
        and the page's KPI count groups of people; the table still lists the virtual row, badged, and the heading
        says how many (OB1, pass 3 of #167)."""
        self._open(dash)
        assert dash.locator("tr[data-ns='ns0'] td.num").first.inner_text().strip() == "0"
        dash.locator("tr[data-ns='ns0'] button.drill").click()
        dash.wait_for_selector("h2:text-is('ns0')")
        kpi = dash.locator(".kpi", has_text="Via groups").locator(".value").inner_text().strip()
        assert kpi == "0", kpi
        head = dash.locator("h2", has_text="Who reaches it").inner_text()
        assert "· 0 · 1 platform" in head, head
        assert dash.locator("tr[data-group='system:serviceaccounts:ns0']").count() == 1, "the virtual row is still listed"

    def test_a_baseline_row_reads_first_observed_not_granted(self, dash):
        """#177's rule: a consumer renders a baseline row as "first observed", never as "added" — the cell
        read "+ granted (first observed)" (OB1 F4). The seed wrote prod-ns's three bindings in its first
        refresh, so all three are baseline rows."""
        self._open(dash)
        dash.locator("tr[data-ns='prod-ns'] button.drill").click()
        dash.wait_for_selector("h2:text-is('prod-ns')")
        cells = dash.locator("td[class^='change-']").evaluate_all("els => els.map(e => e.innerText.replace(/\\s+/g, ' ').trim())")
        assert cells and all(c == "first observed" for c in cells), cells

    def test_a_namespace_change_repaints_on_the_timer_path(self, dash):
        """`data.namespaces` and `data.ns` were written by refresh() but left out of the unchanged-payload
        fingerprint, so an automatic poll whose only change was namespace data skipped the repaint and the
        card sat on a label the wire no longer carried (Codex, review of #167)."""
        import json as _json
        self._open(dash)
        assert dash.locator("tr[data-ns='prod-ns'] td.mono").first.inner_text().strip() == "demo"

        def relabel(route):
            body = route.fetch().json()
            for n in body["namespaces"]:
                if n["name"] == "prod-ns":
                    n["labels"]["company.net/mnemonic"] = "relabelled"
            route.fulfill(status=200, content_type="application/json", body=_json.dumps(body))

        dash.route("**/api/clusters/*/namespaces", relabel)
        dash.evaluate("() => refresh({auto: true})")
        dash.wait_for_function("() => document.querySelector(\"tr[data-ns='prod-ns'] td.mono\").innerText.trim() === 'relabelled'")
def _fleet_server(tmp_path_factory, n: int):
    """The UI seed plus (n - 2) extra clusters, each polled once and refused — an unreachable cluster is
    a legitimate tile ("auth_failed", counts frozen) and a critical alert, which is what the density
    tiers, the worst-first order and the alert pager need in quantity (#172)."""
    db = str(tmp_path_factory.mktemp("gsd") / "fleet.db")
    _seed(db)
    extra = [f"fleet-{i:02d}" for i in range(n - 2)]
    store = Store(db)
    try:
        for cid in extra:
            store.upsert_cluster(cid, f"https://api.{cid}.example.internal:6443", True)
            store.record_poll(cid, "auth_failed", "401 Unauthorized — token invalid or expired")
    finally:
        store.close()
    settings = Settings(
        clusters=[ClusterConfig("crc-local", "https://api.crc.testing:6443", token_env="X"),
                  ClusterConfig("prod-east", "https://api.prod-east.example.com:6443", token_env="Y")]
                 + [ClusterConfig(cid, f"https://api.{cid}.example.internal:6443", token_env="Z") for cid in extra],
        db_path=db, login_capture_enabled=True, view_restrictions_enabled=False,
    )
    port = _free_port()
    app = build_app(settings, run_poller=False)
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(f"{base}/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        raise RuntimeError("fleet server did not start")
    return srv, thread, base


@pytest.fixture(scope="module", params=[2, 6, 14, 40], ids=lambda n: f"{n}-clusters")
def fleet(request, tmp_path_factory):
    srv, thread, base = _fleet_server(tmp_path_factory, request.param)
    yield request.param, base
    srv.should_exit = True
    thread.join(timeout=5)


class TestOverviewFleet:
    """#172: the Overview follows the fleet. Measured against the mock's thresholds (3 / 8 / 24) and
    the live page's one-stack navigation, on a seeded fleet of 2, 6, 14 and 40 clusters."""
    TIER = {2: "full", 6: "medium", 14: "compact", 40: "dense"}

    def _open(self, page, base, hash_="#page=overview"):
        """Named, not default — see `_open_fleet` above."""
        page.goto(f"{base}/{hash_}")
        page.wait_for_selector(".hero .value")
        return page

    def test_density_follows_the_fleet_not_the_viewport(self, page, fleet):
        n, base = fleet
        self._open(page, base)
        assert page.evaluate("() => document.documentElement.dataset.density") == self.TIER[n]
        if n > 24:
            assert page.locator("tr.rowlink[data-cluster]").count() == n and page.locator(".tile").count() == 0
        else:
            assert page.locator(".tile").count() == n
            api_visible = page.locator(".tile .api").first.is_visible()
            assert api_visible == (n <= 3), "the API line belongs to the full tier only"
            assert page.locator(".tile .k-extra").first.is_visible() == (n <= 3), "the three extra figures belong to the full tier only (the mock's tiers)"
        page.set_viewport_size({"width": 375, "height": 740})
        assert page.evaluate("() => document.documentElement.dataset.density") == self.TIER[n], "density is the fleet's, not the viewport's"
        assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")

    def test_worst_first_past_three_and_alerts_lead_past_eight(self, page, fleet):
        n, base = fleet
        self._open(page, base)
        order = page.evaluate("() => [...document.querySelectorAll('#main > section, #main > div')].map(e => e.className.split(' ')[0])")
        if n <= 3:
            first = page.locator(".tile h2").first.inner_text().strip()
            assert first == "crc-local", "below four clusters the order is the served order, not worst-first"
            assert order.index("tiles") < order.index("card"), "the tiles lead a small fleet"
        else:
            sel = "tr.rowlink[data-cluster] .badge" if n > 24 else ".tile .badge"
            assert page.locator(sel).first.inner_text().strip() != "reachable", "past three clusters the worst tile comes first"
        if n > 8:
            first_card = page.locator("#main > section.card").first
            assert first_card.locator(".hero .value").count() == 1, "past eight clusters the alerts lead the page"

    def test_alerts_are_paged_and_the_page_is_view_state(self, page, fleet):
        n, base = fleet
        self._open(page, base)
        pager = page.locator(".pager")
        total = len(httpx.get(f"{base}/api/alerts", timeout=5).json()["alerts"])
        if total <= 8:
            assert pager.count() == 0, "eight or fewer alerts need no pager"
            return
        assert pager.count() == 1, f"{total} alerts need a pager"
        assert page.locator(".alert-row").count() == 8
        first_before = page.locator(".alert-row .who").first.inner_text()
        page.get_by_role("button", name="2", exact=True).click()   # the numbered button, not "Next ›"
        page.wait_for_function("() => document.querySelector(\"button[data-alert-page='2'][aria-pressed='true']\")")
        assert page.locator(".alert-row .who").first.inner_text() != first_before
        assert page.evaluate("() => location.hash") in ("", "#page=overview"), "a page click is not a position"
        page.click("#tab-groups")
        page.wait_for_selector("#tab-groups[aria-current='page']")
        page.click("#tab-overview")
        page.wait_for_selector("button[data-alert-page='1'][aria-pressed='true']")

    def test_a_tile_opens_the_cluster_and_back_returns_to_the_fleet(self, page, fleet):
        n, base = fleet
        self._open(page, base)
        opener = "tr.rowlink[data-cluster='crc-local']" if n > 24 else ".tile[data-cluster='crc-local']"
        _open_cluster(page, opener)
        assert page.evaluate("() => location.hash") == "#page=overview&cluster=crc-local"
        assert page.locator("#back").inner_text().strip() == "← all clusters"
        assert page.locator("#f-cluster").input_value() == "crc-local", "the selector is the same position as the tile"
        assert page.locator("h2", has_text="GroupSync CRs").count() == 1
        assert "on crc-local" in page.locator("#main").inner_text()
        assert "across 1 cluster" in page.locator(".hero .label").inner_text(), "the scoped view counts one cluster's alerts"
        page.locator("#back").click()
        # The position changes at once; the repaint follows the refetch — wait for the selector to say so.
        page.wait_for_function("() => document.getElementById('f-cluster').value === '' && !document.querySelector('#back')")
        assert page.evaluate("() => location.hash") in ("#page=overview", "")
        page.locator(opener).click()
        page.wait_for_selector("#back")
        page.go_back()
        page.wait_for_function("() => document.getElementById('f-cluster').value === '' && !document.querySelector('#back')")
        assert page.locator(".tile, tr.rowlink[data-cluster]").count() >= 2, "the browser's Back walks the same stack to the fleet"

    def test_the_selector_opens_the_same_scoped_view(self, page, fleet):
        n, base = fleet
        self._open(page, base)
        page.select_option("#f-cluster", "prod-east")
        page.wait_for_selector("#back")
        assert page.evaluate("() => location.hash") == "#page=overview&cluster=prod-east"
        assert "401 Unauthorized" in page.locator("#main").inner_text()
        assert "the poller cannot reach it" in page.locator("#main").inner_text(), "an unreachable cluster states its consequence"

    def test_the_contract_survives_in_both_views(self, page, fleet):
        n, base = fleet
        self._open(page, base)
        text = page.locator("#main").inner_text()
        if n <= 8:
            assert "GroupSync CRs" in page.locator("section.card h2").all_inner_texts()
            for col in ("Name", "State", "Schedule", "Groups", "Last sync", "Next expected"):
                assert page.locator("th", has_text=col).count() >= 1, col
            assert "Policy operator (NamespaceConfig / GroupConfig)" in text
            assert "quietly stopped reconciling" in text
        _open_cluster(page, "tr.rowlink[data-cluster='crc-local']" if n > 24 else ".tile[data-cluster='crc-local']")
        # text_content: the labels are not upper-cased (OB1 measured text-transform none), but text_content
        # also reads the figures the density tier hides, which is the point — the scoped view carries them all
        text = page.locator("#main").text_content()
        for label in ("Groups", "Bindings to review", "Unattributed", "Oldest last sync", "GroupSync CRs", "Empty", "Policy configs"):
            assert label in text, f"the scoped view dropped the figure {label!r}"
        assert "Policy operator (NamespaceConfig / GroupConfig)" in text and "quietly stopped reconciling" in text
        row = page.locator("tr[data-cr='bda-rbac-groupsync']")
        assert "overdue" in row.inner_text() and "the schedule has stopped firing" in row.inner_text(), "overdue states its consequence"
        ok_row = page.locator("tr[data-cr='ldap-groupsync']")
        assert "ok" in ok_row.inner_text() and "frozen" not in ok_row.inner_text()
        badges = [b.strip() for b in page.locator("tr[data-cr] .badge").all_inner_texts()]
        assert not ({"critical", "warning"} & set(badges) - {"reconcile error"}) or all(b in ("ok", "late", "overdue", "unknown", "reconcile error") for b in badges), badges


def _review_server(tmp_path_factory, n: int, *, retired=(), badcron=False, restricted=False):
    """`_fleet_server` plus what the review of #172 needed: a CR with an unusable schedule, a retired
    cluster (#96), restrictions on (the scoped_server shape — proxy on, the tier keyed off X-Forwarded-User)."""
    from datetime import UTC as _UTC
    db = str(tmp_path_factory.mktemp("gsd") / "review.db")
    _seed(db)
    extra = [f"fleet-{i:02d}" for i in range(n - 2)]
    store = Store(db)
    try:
        for cid in extra:
            store.upsert_cluster(cid, f"https://api.{cid}.example.internal:6443", True)
            store.record_poll(cid, "auth_failed", "401 Unauthorized — token invalid or expired")
        for cid in retired:                      # #96: removed from config, enabled=0, history kept
            store.upsert_cluster(cid, f"https://api.{cid}.example.internal:6443", False)
        if badcron:                              # synced 3 min ago on a reachable cluster; the schedule is the defect
            rows = [dict(r) for r in store.groupsyncs("crc-local")]
            now = datetime.now(_UTC)
            rows.append({"name": "badcron-groupsync", "namespace": "group-sync-operator", "schedule": "not a cron",
                         "ldap_filter": "(cn=x)", "last_sync_at": _iso(now - timedelta(minutes=3)), "generation": 1,
                         "provider_keys": ["badcron-groupsync_ldap"]})
            rows.append({"name": "nevercron-groupsync", "namespace": "group-sync-operator", "schedule": "not a cron",
                         "ldap_filter": "(cn=y)", "last_sync_at": None, "generation": 1,
                         "provider_keys": ["nevercron-groupsync_ldap"]})
            store.replace_groupsync_state("crc-local", rows, _iso(now))
    finally:
        store.close()
    kw = {"oauth_proxy_enabled": True} if restricted else {"view_restrictions_enabled": False}
    settings = Settings(
        clusters=[ClusterConfig("crc-local", "https://api.crc.testing:6443", token_env="X"),
                  ClusterConfig("prod-east", "https://api.prod-east.example.com:6443", token_env="Y")]
                 + [ClusterConfig(cid, f"https://api.{cid}.example.internal:6443", token_env="Z") for cid in extra],
        db_path=db, login_capture_enabled=True, **kw,
    )
    port = _free_port()
    app = build_app(settings, run_poller=False)
    if restricted:
        app.state.tier_resolver = _TierByName()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(f"{base}/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        raise RuntimeError("review server did not start")
    return srv, thread, base, db


def _serve_review(tmp_path_factory, n, **opts):
    srv, thread, base, db = _review_server(tmp_path_factory, n, **opts)
    yield base, db
    srv.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def review_two(tmp_path_factory):
    yield from _serve_review(tmp_path_factory, 2, retired=("gone-cluster",), badcron=True)


@pytest.fixture(scope="module")
def review_compact(tmp_path_factory):
    yield from _serve_review(tmp_path_factory, 14)


@pytest.fixture(scope="module")
def review_dense(tmp_path_factory):
    yield from _serve_review(tmp_path_factory, 40)


@pytest.fixture(scope="module")
def review_restricted(tmp_path_factory):
    yield from _serve_review(tmp_path_factory, 2, restricted=True)


def _open_fleet(page, base, hash_="#page=overview"):
    """The fleet, at a NAMED position. The default route is not this page's to assume: #158 makes Home the
    landing page for every tier, and these tests — which live on a sibling branch and so never saw that
    change — waited 30 s for a hero Home does not have, 37 times, the first time the two were merged. A
    test names the page it is about."""
    page.goto(f"{base}/{hash_}")
    page.wait_for_selector(".hero .value")


def _open_cluster(page, opener):
    """Click a tile (or a dense row) and wait for the scoped view to paint its TABLES. `#back` arrives with
    the first paint — the tile, its alerts and "Loading…" (F15: a tile paints before it fetches); the
    GroupSync CRs and policy tables land with the batch's one render. A test that reads them after `#back`
    alone reads the Loading frame when the runner is slow enough: CI did, at 14 clusters (run 35342604962,
    350 passed beside it, every local run green) — the wait on the position, not the paint, that OB1 found
    in the e2e walk (pass 3, C6)."""
    page.locator(opener).click()
    page.wait_for_selector("#back")
    page.wait_for_function("() => !document.getElementById('main').innerText.includes('Loading…')")


class TestOverviewReview:
    """The review of #172 (docs/REVIEW_overview_relayout.md): one test per accepted finding, each shown
    failing on 759cd7d. Grok read the source; OB1 drove the app at 2/6/14/40 clusters and supplied the
    fixtures and most of these tests; Codex read the contract."""

    def test_unknown_state_names_the_schedule_not_the_cluster(self, page, review_two):
        """`unknown` on the wire is never "unreachable" — api.enrich() passes no `reachable` to
        compute_state(); with a last sync and schedule_valid false it is the schedule (OB1 F1)."""
        base, _ = review_two
        _open_fleet(page, base)
        row = page.locator("tr[data-cr='badcron-groupsync']")
        assert "unknown" in row.locator(".badge").first.inner_text()
        consq = row.locator(".consq").inner_text()
        assert "schedule" in consq, consq
        assert "unreachable" not in consq and "never observed" not in consq, consq

    def test_dense_rows_carry_the_reachability_badge(self, page, review_dense):
        """badge("critical") is a word outside STATES → "unknown" for every auth_failed row (Grok F2, OB1 F2)."""
        base, _ = review_dense
        _open_fleet(page, base)
        b = page.locator("tr.rowlink[data-cluster='prod-east'] .badge")
        assert b.inner_text().strip() == "auth_failed"
        assert "critical" in b.get_attribute("class") and "unknown" not in b.get_attribute("class")

    def test_absent_note_needs_a_successful_poll(self, page, review_two):
        """The store's `present` is two-valued, so a never-polled or failed-poll cluster reads present:false too;
        "prod-east reports these CRDs absent" was said of a cluster that reported nothing (OB1 F3)."""
        base, _ = review_two
        _open_fleet(page, base)
        notes = [t for t in page.locator(".filterbar-note").all_inner_texts() if "absent" in t]
        assert not any("prod-east" in t for t in notes), notes

    def test_the_opened_cluster_has_no_dead_button_and_keeps_the_tile_typography(self, page, review_two):
        """A string-replaced tile kept an inert heading button and lost every .tile-scoped style (Grok F3, OB1 F4)."""
        base, _ = review_two
        _open_fleet(page, base, "#page=overview&cluster=crc-local")
        page.wait_for_selector(".tile-detail")
        assert page.locator(".tile-detail button.tile-open").count() == 0, "a button that opens where the reader already is"
        assert page.locator(".tile-detail h2").inner_text().strip() == "crc-local"
        api = page.evaluate("() => { const s = getComputedStyle(document.querySelector('.tile-detail .api')); return [s.display, s.fontFamily]; }")
        assert api[0] == "block", api
        assert "mono" in api[1].lower(), api
        assert page.evaluate("() => getComputedStyle(document.querySelector('.tile-detail .cn')).fontWeight") in ("600", "700", "bold")

    def test_a_tile_opened_from_the_fleet_drops_the_previous_clusters_payloads(self, page, review_two):
        """The orphan-clearing chokepoint was guarded on `view.cluster &&`; the fleet leaves it null, so a tile
        opened after a scoped visit cleared nothing and the next tab painted crc-local's groups under
        prod-east (OB1 F5; the same hole found tracing Grok's paint-first snippet)."""
        base, _ = review_two
        page.goto(f"{base}/#page=groups&cluster=crc-local")
        page.wait_for_selector("tr[data-group]")
        page.click("#tab-overview")
        page.wait_for_function("() => view.cluster === null && document.querySelector('.tile')")
        page.locator(".tile[data-cluster='prod-east']").click()
        page.wait_for_selector("#back")
        painted = page.evaluate("""() => { document.querySelector('#tab-groups').click();
            return {cluster: view.cluster, rows: document.querySelectorAll('tr[data-group]').length}; }""")
        assert painted["cluster"] == "prod-east"
        assert painted["rows"] == 0, f"crc-local's groups painted under prod-east: {painted}"

    def test_a_tile_paints_the_cluster_before_its_fetch_returns(self, page, review_two):
        """The tab handler paints the destination before it fetches; a tile did navigate(); refresh() and left
        the dimmed fleet on screen for the length of the round trip (Grok F5). The first paint is the tile,
        its alerts and "Loading…" — no other cluster's CRs."""
        base, _ = review_two
        _open_fleet(page, base)
        held = []
        page.route("**/api/clusters/prod-east/groupsyncs", lambda route: held.append(route))
        page.locator(".tile[data-cluster='prod-east']").click()
        page.wait_for_selector("#back", timeout=3000)
        assert "Loading" in page.locator("#main").inner_text()
        assert page.locator("tr[data-cr]").count() == 0, "another cluster's CRs under prod-east"
        for route in held:
            route.continue_()
        page.wait_for_function("() => !document.querySelector('#main').innerText.includes('Loading')")

    def test_the_fleet_tables_say_loading_not_per_cluster_while_the_fetch_is_out(self, page, review_two):
        """Below nine clusters a missing fleet payload is a fetch still out, not the per-cluster note (OB1 F6)."""
        base, _ = review_two
        page.goto(f"{base}/#page=groups&cluster=crc-local")
        page.wait_for_selector("tr[data-group]")
        first = page.evaluate("""() => { document.querySelector('#tab-overview').click();
            return (document.querySelector('#main .empty-note') || {}).textContent || ''; }""")
        assert "shown per cluster" not in first, first
        assert "Loading" in first, first

    def test_an_auto_refresh_repaints_the_fleet_tables_when_only_they_changed(self, page, review_two):
        """data.fleet is rendered and was not fingerprinted (Grok F4, OB1 F7, Codex F4)."""
        from datetime import UTC as _UTC
        base, db = review_two
        _open_fleet(page, base)
        page.wait_for_selector("tr[data-cr='ldap-groupsync']")
        cell = "() => document.querySelector(\"tr[data-cr='ldap-groupsync'] code\").textContent"
        assert page.evaluate(cell) == "*/30 * * * *"
        store = Store(db)
        try:
            rows = [dict(r) for r in store.groupsyncs("crc-local")]
            for r in rows:
                if r["name"] == "ldap-groupsync":
                    r["schedule"] = "*/20 * * * *"      # still ok at a 4-minute age: no alert, no cluster count moves
            store.replace_groupsync_state("crc-local", rows, _iso(datetime.now(_UTC)))
        finally:
            store.close()
        page.evaluate("() => refresh({auto: true})")
        page.wait_for_function("""() => document.querySelector("tr[data-cr='ldap-groupsync'] code").textContent === '*/20 * * * *'""", timeout=5000)

    def test_a_failed_cluster_fetch_is_named_on_the_fleet_table(self, page, review_two):
        """A cluster whose /groupsyncs request failed was folded into "all syncing" (OB1 F8)."""
        base, _ = review_two
        page.route("**/api/clusters/prod-east/groupsyncs", lambda route: route.fulfill(status=500, body="boom"))
        _open_fleet(page, base)
        page.wait_for_selector("tr[data-cr]")
        text = page.locator("#main").inner_text()
        assert "prod-east: CRs not fetched" in text, text[:400]

    def test_a_narrowed_reader_does_not_fetch_the_fleet_tables(self, browser, review_restricted):
        """A refused reader's browser ran the fleet stage every poll — N designed 403s a minute on /metrics
        for a page they cannot see (OB1 F9)."""
        base, _ = review_restricted
        ctx = browser.new_context(extra_http_headers={"X-Forwarded-User": "alice"})
        page = ctx.new_page()
        hits = []
        page.on("request", lambda r: hits.append(r.url) if "/api/clusters/" in r.url else None)
        page.goto(base + "/#page=overview")   # the Overview's refusal is the subject; #158 moved the landing page
        page.wait_for_function("() => document.querySelector('#main').innerText.includes('Withheld')")
        page.evaluate("() => refresh({auto: true})")
        page.wait_for_timeout(1000)
        ctx.close()
        assert hits == [], hits

    def test_a_link_to_a_retired_cluster_is_a_detour_with_the_bar_intact(self, page, review_two):
        """#96: the API 404s a retired id, the batch rejected, render() never ran — the generic error card with
        no tab bar, and the page's own note unreachable (Grok F1, OB1 F10, Codex F2)."""
        base, _ = review_two
        page.goto(f"{base}/#page=overview&cluster=gone-cluster")
        page.reload()
        page.wait_for_function("() => document.querySelector('#main').innerText.includes('No cluster by that id')", timeout=8000)
        assert page.locator("#f-cluster").count() == 1, "the filter bar never rendered"
        assert "Dashboard API error" not in page.locator("#main").inner_text()
        page.locator("#back").click()
        page.wait_for_function("() => view.cluster === null && document.querySelector('.tile')")

    def test_a_superseded_refresh_does_not_write_the_fleet_payload(self, page, review_two):
        """data.fleet was written before the superseded check — the codebase's own "must not WRITE" rule
        (OB1 F11). The supersede happens from inside the fleet stage's own request, so it is not a race."""
        base, _ = review_two
        _open_fleet(page, base)
        page.wait_for_selector("tr[data-cr]")

        def supersede_then_answer(route):
            page.evaluate("() => { navigate({cluster: 'crc-local'}); refresh(); }")
            route.continue_()

        page.route("**/api/clusters/prod-east/groupsyncs", supersede_then_answer)
        page.evaluate("() => { data.fleet = 'SENTINEL'; refresh({auto: true}); }")
        page.wait_for_selector("#back")
        page.wait_for_timeout(1200)
        assert page.evaluate("() => data.fleet") == "SENTINEL", "the superseded refresh wrote data.fleet"

    def test_the_opened_cluster_keeps_the_tile_rail(self, page, review_two):
        """Pass 2 (Grok V3): F4 paired .cn/.api/.poll onto .tile-detail and left .tile.bad behind, so an
        opened auth_failed cluster looked healthier than its tile."""
        base, _ = review_two
        _open_fleet(page, base)
        rail = "() => { const t = document.querySelector(SEL); const s = getComputedStyle(t); return [t.className, s.borderLeftWidth, s.borderLeftColor]; }"
        tile_rail = page.evaluate(rail.replace("SEL", "'.tile[data-cluster=\"prod-east\"]'"))
        page.locator(".tile[data-cluster='prod-east']").click()
        page.wait_for_selector(".tile-detail")
        detail_rail = page.evaluate(rail.replace("SEL", "'.tile-detail'"))
        assert "bad" in detail_rail[0]
        assert detail_rail[1] == tile_rail[1] == "3px", (tile_rail, detail_rail)
        assert detail_rail[2] == tile_rail[2]

    def test_the_selector_names_a_retired_id_beside_its_detour(self, page, review_two):
        """Pass 2 (Grok V1): the detour rendered with the selector on its first option, "all clusters",
        for a page that is not the fleet."""
        base, _ = review_two
        page.goto(f"{base}/#page=overview&cluster=gone-cluster")
        page.reload()
        page.wait_for_function("() => document.querySelector('#main').innerText.includes('No cluster by that id')")
        assert page.evaluate("() => [document.getElementById('f-cluster').value, view.cluster]") == ["gone-cluster", "gone-cluster"]
        assert "not configured" in page.locator("#f-cluster option:checked").inner_text()
        page.locator("#back").click()
        page.wait_for_function("() => view.cluster === null && document.querySelector('.tile')")
        assert page.locator("#f-cluster").input_value() == ""

    def test_a_heading_beside_its_count_keeps_the_accent_rail(self, page, review_two):
        """Pass 2 (Grok V4): `.card > h2::before` never matched a heading inside `.row-wrap`, so the
        GroupSync card on the Overview and the Policy card lost their 3 px accent rail."""
        base, _ = review_two
        _open_fleet(page, base, "#page=overview&cluster=crc-local")
        page.wait_for_selector("h3:has-text('Policy operator')")
        widths = page.evaluate("""() => ['GroupSync CRs', 'Policy operator'].map(t => {
            const h = [...document.querySelectorAll('#main h2, #main h3')].find(e => e.textContent.includes(t));
            return getComputedStyle(h, '::before').width; })""")
        assert widths == ["3px", "3px"], widths

    def test_unknown_without_a_last_sync_still_names_an_unusable_schedule(self, page, review_two):
        """Pass 2 (Grok V2): the schedule sentence was gated on a last sync, so a never-synced CR with an
        unusable schedule read "until its first fire" — of a cron that cannot fire."""
        base, _ = review_two
        _open_fleet(page, base)
        consq = page.locator("tr[data-cr='nevercron-groupsync'] .consq").inner_text()
        assert "schedule" in consq and "never observed" not in consq, consq

    def test_kinds_are_chips_not_blank_badges(self, page, review_compact):
        """A .badge with no state class drew a 9 px transparent square where a glyph belongs (OB1 F13)."""
        base, _ = review_compact
        _open_fleet(page, base)
        assert page.locator(".kinds .kind").count() > 0
        assert page.locator(".kinds .badge").count() == 0

    def test_a_tile_heading_carries_no_accent_rail_like_its_opened_form(self, page, review_two):
        """Pass 2 widened the accent-rail selector to `.card > .row-wrap > h2::before` for the counted headings,
        and it matched every tile's name heading too: a 3 px accent rail 16 px inboard of the tile's own 3 px
        status rail, which the mock's tile (a button, not a card) never had, the pre-#172 cluster card never had,
        and the opened cluster (.tile-detail, not a direct child of .card) does not have (OB1, pass 3). The tile
        and its opened form agree — neither name wears the accent rail — and the counted headings keep theirs."""
        base, _ = review_two
        _open_fleet(page, base)
        page.wait_for_selector("tr[data-cr]")
        rail = "(sel) => getComputedStyle(document.querySelector(sel), '::before').width"
        tile = page.evaluate(rail, ".tile[data-cluster='prod-east'] h2")
        counted = page.evaluate("() => getComputedStyle([...document.querySelectorAll('#main h2')].find(h => h.textContent.includes('GroupSync CRs')), '::before').width")
        page.locator(".tile[data-cluster='prod-east']").click()
        page.wait_for_selector(".tile-detail h2")
        detail = page.evaluate(rail, ".tile-detail h2")
        assert tile == detail, (tile, detail)
        assert tile != "3px" and counted == "3px", (tile, counted)


def _e2e_walk_module():
    """`local-development/e2e-walk/` is not a package; `e2e_capture.py` is loaded by path, as the walk's
    own unit test loads it, so a helper the walk relies on can be driven against a seeded server here."""
    path = pathlib.Path(__file__).resolve().parents[1] / "e2e-walk" / "e2e_capture.py"
    spec = importlib.util.spec_from_file_location("gsd_e2e_capture_ui", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def slow_cluster_server(tmp_path_factory):
    """The seeded two-cluster app behind an ASGI wrapper that holds prod-east's GroupSync payload for
    1.2 s: the walk's cluster switch has to wait through a route's round trip, not loopback's."""
    db = str(tmp_path_factory.mktemp("gsd") / "slow.db")
    _seed(db)
    settings = Settings(
        clusters=[ClusterConfig("crc-local", "https://api.crc.testing:6443", token_env="X"),
                  ClusterConfig("prod-east", "https://api.prod-east.example.com:6443", token_env="Y")],
        db_path=db, login_capture_enabled=True, view_restrictions_enabled=False,
    )
    app = build_app(settings, run_poller=False)
    held = {"/api/clusters/prod-east/groupsyncs": 1.2}

    async def slow(scope, receive, send):
        if scope["type"] == "http" and scope["path"] in held:
            await asyncio.sleep(held[scope["path"]])
        await app(scope, receive, send)

    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(slow, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(f"{base}/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        raise RuntimeError("slow cluster server did not start")
    yield base
    srv.should_exit = True
    thread.join(timeout=5)


def test_the_walks_cluster_switch_waits_for_the_paint_not_the_position(page, slow_cluster_server):
    """`view.cluster` changes the instant the selector fires, and `wait_for_load_state("networkidle")`
    resolves at once when the document has already reached that state — so the walk's second-cluster wait
    returned with the previous cluster still on screen, and its 900 ms sleep was the only cover (measured
    with the fetch held 1.5 s: the heading stale after networkidle at 24 ms and after the sleep at 941 ms —
    OB1, review of #172, pass 3). The helper returns when the opened cluster names the id and #main is no
    longer dimmed, however long the route takes."""
    wait_for_cluster_paint = _e2e_walk_module().wait_for_cluster_paint
    page.goto(f"{slow_cluster_server}/#page=overview")   # the tile is the subject; #158 moved the landing page
    page.wait_for_selector(".tile[data-cluster='prod-east']")
    started = time.monotonic()
    page.locator("select#f-cluster").select_option(value="prod-east")
    wait_for_cluster_paint(page, "prod-east")
    waited = time.monotonic() - started
    assert page.locator("h2").first.inner_text().strip() == "prod-east"
    assert not page.evaluate("() => document.getElementById('main').classList.contains('stale')")
    assert waited >= 1.0, f"returned after {waited:.2f}s with the fetch held 1.2 s: the position, not the paint"



@pytest.fixture(scope="module")
def two_polled_server(tmp_path_factory):
    """The UI seed with prod-east polled and holding two groups of its own, so a payload painted under the
    wrong cluster shows as ROWS rather than as an empty list."""
    db = str(tmp_path_factory.mktemp("gsd-two") / "ui.db")
    _seed(db)
    now = datetime.now(UTC)
    store = Store(db)
    try:
        store.record_poll("prod-east", "ok", None)
        store.replace_group_state("prod-east", [
            {"name": "east-only-group-one", "member_count": 1, "sync_provider": "east-sync_ldap",
             "group_synced_at": _iso(now - timedelta(minutes=2)), "ldap_uid": "cn=east-only-group-one,ou=Groups,dc=example,dc=com"},
            {"name": "east-only-group-two", "member_count": 1, "sync_provider": "east-sync_ldap",
             "group_synced_at": _iso(now - timedelta(minutes=2)), "ldap_uid": "cn=east-only-group-two,ou=Groups,dc=example,dc=com"},
        ], _iso(now))
        store.sync_members("prod-east", {"east-only-group-one": ["erin"], "east-only-group-two": ["erin"]}, {},
                           _iso(now - timedelta(minutes=2)))
    finally:
        store.close()
    settings = Settings(
        clusters=[ClusterConfig("crc-local", "https://api.crc.testing:6443", token_env="X"),
                  ClusterConfig("prod-east", "https://api.prod-east.example.com:6443", token_env="Y")],
        db_path=db, login_capture_enabled=True, view_restrictions_enabled=False,
    )
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(build_app(settings, run_poller=False), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(f"{base}/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        raise RuntimeError("two-polled server did not start")
    yield base
    srv.should_exit = True
    thread.join(timeout=5)


class TestTheFleetOrphansNoPayload:
    """#172 made "no cluster" a position (the fleet), and the tab handler paints from `data` before it
    fetches. The chokepoint dropped the cluster-scoped payloads on a change BETWEEN clusters and on the way
    FROM no cluster, but not on the way TO none — so Groups on prod-east → Overview (the fleet) → Groups
    painted prod-east's rows under `#page=groups&cluster=crc-local` for the length of the fetch (OB3,
    integration review, C2: measured 300 ms after the click)."""

    def test_a_tab_opened_from_the_fleet_never_paints_the_previous_clusters_rows(self, page, two_polled_server):
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{two_polled_server}/#page=groups&cluster=prod-east")
        page.wait_for_selector("tr[data-group='east-only-group-one']")
        page.click("#tab-overview")
        page.wait_for_selector(".tile[data-cluster='crc-local']")
        assert page.evaluate("() => view.cluster") is None, "the Overview tab opens the fleet"
        held: list = []
        page.route("**/api/clusters/*/groups?*", lambda route: held.append(route))   # hold the fetch; read the first paint
        page.click("#tab-groups")
        page.wait_for_function("() => location.hash === '#page=groups&cluster=crc-local'")   # boot stamped the default
        first = page.evaluate("""() => ({rows: [...document.querySelectorAll('tr[data-group]')].map(t => t.dataset.group),
                                        loading: document.getElementById('main').innerText.includes('Loading…')})""")
        for route in held:
            route.continue_()
        page.unroute("**/api/clusters/*/groups?*")
        assert first["rows"] == [] and first["loading"], f"another cluster's rows under crc-local's position: {first}"
        page.wait_for_selector("tr[data-group='app-ocp-rbac-alpha-ns-admin']")
        assert page.evaluate("() => document.getElementById('scope-note').textContent") == " - crc-local"
        assert not errors


class TestLookup:
    """#174: one lookup over the three kinds — three doors at rest, matches by kind with text, the AND
    contract of the list boxes (`alice zzz` finds nothing), the also-line on a list page and
    "search everything instead" inside a group carrying the text across ONE position change."""

    def test_start_anywhere_doors_carry_the_lists_own_counts(self, page, server):
        page.goto(f"{server}/#page=lookup&cluster=crc-local")
        page.wait_for_selector(".door")
        page.wait_for_function("() => [...document.querySelectorAll('.door .value')].every(v => v.textContent.trim() !== '…')")
        doors = {d["kind"]: int(d["n"]) for d in page.evaluate(
            "() => [...document.querySelectorAll('.door')].map(d => ({kind: d.querySelector('.label').textContent.trim(), n: d.querySelector('.value').textContent.trim()}))")}
        api = f"{server}/api/clusters/crc-local"
        assert doors["Groups"] == httpx.get(f"{api}/groups?state=all", timeout=5).json()["count"]
        assert doors["Users"] == httpx.get(f"{api}/users?limit=10000", timeout=5).json()["total"]
        assert doors["Namespaces"] == httpx.get(f"{api}/namespaces", timeout=5).json()["count"] == 9
        page.locator(".door[data-page='groups'] button.drill").click()
        page.wait_for_selector("tr[data-group]")
        assert page.evaluate("() => location.hash") == "#page=groups&cluster=crc-local"

    def test_typing_where_nothing_filters_opens_the_lookup_once(self, dash):
        before = dash.evaluate("() => history.length")
        dash.fill("#f-lookup-search", "alice")
        dash.wait_for_selector("tr[data-user='alice']")
        assert dash.evaluate("() => [view.page, location.hash]") == ["lookup", "#page=lookup&cluster=crc-local"]
        assert dash.evaluate("() => history.length") == before + 1, "one position change, not one per keystroke"
        assert dash.locator("#f-lookup-search").input_value() == "alice", "the text is carried"
        dash.fill("#f-lookup-search", "alice cooper")
        dash.wait_for_selector("tr[data-user='alice'] mark")
        assert dash.evaluate("() => history.length") == before + 1, "typing on the lookup is a repaint"

    def test_the_lookup_ands_its_words_across_three_kinds(self, page, server):
        page.goto(f"{server}/#page=lookup&cluster=crc-local")
        page.wait_for_selector(".door")
        page.fill("#f-lookup-search", "alice zzz")
        page.wait_for_selector("#main .empty-note")
        assert "The data is not empty" in page.locator("#main .empty-note").inner_text()
        assert page.locator("tr[data-user], tr[data-group], tr[data-ns]").count() == 0
        page.fill("#f-lookup-search", "demo")
        page.wait_for_selector("tr[data-ns='prod-ns']")
        assert sorted(page.locator("tr[data-ns]").evaluate_all("els => els.map(e => e.dataset.ns)")) == ["prod-ns", "quiet-corner"], "by label value"
        assert page.locator("tr[data-ns='prod-ns'] mark").count() >= 1, "the matched substring is marked"
        page.fill("#f-lookup-search", "rbac alpha")
        page.wait_for_selector("tr[data-group]")
        groups = page.locator("tr[data-group]").evaluate_all("els => els.map(e => e.dataset.group)")
        assert groups and all("rbac" in g and "alpha" in g for g in groups), groups
        assert "of" in page.locator("h3", has_text="Groups").inner_text()
        page.press("#f-lookup-search", "Escape")
        page.wait_for_selector(".door")

    def test_the_also_line_on_a_list_offers_the_other_kinds_and_carries_the_text(self, dash):
        """Typing is a filter and issues no request, and the users list is fetched only on its own tab — so on a
        fresh Groups tab the line is the plain door, and the counts appear only for a kind this session already
        holds (the audit tab visited first). Either way the text is carried to the lookup."""
        dash.click("#tab-groups")
        dash.wait_for_selector("#f-group-search")
        dash.evaluate("() => { window.__urls = []; const f = window.fetch;"
                      " window.fetch = (...a) => { window.__urls.push(String(a[0])); return f(...a); }; }")
        dash.fill("#f-group-search", "demo")
        dash.wait_for_selector("[data-widen]")
        line = dash.locator("[data-widen]").locator("xpath=..").inner_text()
        assert "search everything for demo" in line and "namespaces" not in line, line
        assert dash.evaluate("() => window.__urls") == [], "typing must not fetch"
        dash.locator("[data-widen]").click()
        dash.wait_for_selector("tr[data-ns='prod-ns']")
        assert dash.evaluate("() => [view.page, document.getElementById('f-lookup-search').value]") == ["lookup", "demo"]
        # the audit tab loads the namespaces; back on Groups the line now counts them
        dash.click('button.tab:text-is("Namespace audit")')
        dash.wait_for_selector("tr[data-ns]")
        dash.click("#tab-groups")
        dash.wait_for_selector("#f-group-search")
        dash.fill("#f-group-search", "demo")
        dash.wait_for_function("() => { const w = document.querySelector('[data-widen]'); return !!w && w.parentElement.textContent.includes('2 namespaces'); }")

    def test_search_everything_instead_carries_the_text_out_of_a_group(self, dash):
        dash.click("#tab-groups")
        dash.wait_for_selector("tr[data-group='app-ocp-rbac-alpha-ns-admin']")
        dash.locator("tr[data-group='app-ocp-rbac-alpha-ns-admin']").click()
        dash.wait_for_selector("#f-member-search")
        dash.fill("#f-member-search", "alice")
        dash.wait_for_selector("[data-widen]")
        dash.locator("[data-widen]").click()
        # the group's own members table already lists alice — wait for the LOOKUP to paint, not for a row
        dash.wait_for_function("() => view.page === 'lookup' && document.getElementById('f-lookup-search') && document.querySelector('#main h3')")
        assert dash.locator("#main tr[data-user='alice']").count() == 1
        assert dash.evaluate("() => [view.page, view.group, document.getElementById('f-lookup-search').value]") == ["lookup", None, "alice"]

    # -- the review of #174 (Grok, Codex, OB1 — docs/REVIEW_lookup.md): OB1's thirteen, verbatim, each failing on
    #    76ebaff and on the merged base d489bcc; the fixes are OB1's recipe plus Grok's and Codex's converging findings

    # ── F1: IME and whitespace ──
    def test_a_committed_ime_composition_opens_the_lookup_once(self, dash):
        """Chromium fires no `input` after `compositionend` (measured: input×3 with isComposing=true, then
        compositionend, nothing after), so the rule that opens the lookup from a page with no list has to
        run on the commit too — or a CJK reader's query sits in the box on the Overview and opens nothing."""
        before = dash.evaluate("() => history.length")
        dash.focus("#f-lookup-search")
        cdp = dash.context.new_cdp_session(dash)
        cdp.send("Input.imeSetComposition", {"text": "か", "selectionStart": 1, "selectionEnd": 1})
        dash.wait_for_timeout(150)
        assert dash.evaluate("() => [view.page, history.length]") == ["overview", before], "mid-composition is not a position change"
        cdp.send("Input.insertText", {"text": "かんり"})
        dash.wait_for_function("() => view.page === 'lookup'", timeout=3_000)
        assert dash.evaluate("() => [view.lookupSearch, location.hash, history.length]") == ["かんり", "#page=lookup&cluster=crc-local", before + 1]

    def test_a_query_of_only_spaces_is_not_a_position_change(self, dash):
        before = dash.evaluate("() => history.length")
        dash.type("#f-lookup-search", "   ")
        dash.wait_for_timeout(300)
        assert dash.evaluate("() => [view.page, history.length]") == ["overview", before]

    # ── F2: marking ──
    def test_marking_keeps_the_text_it_marks(self, dash):
        """hl() marked on the ESCAPED string: a one-character term landed inside an entity (`a` in `&amp;`),
        and a second term inside the <mark> the first had just inserted ("alice a" painted "ark>aliceark>").
        The rendered text must be the raw text; every mark must be one of the terms."""
        cases = dash.evaluate("""() => [["Smith & Wesson", "a"], ["Dara O'Brien", "3"], ["Walter Holt <walt@corp.example>", "t"],
              ["alice", "alice a"], ["app-ocp-rbac-alpha-ns-admin", "rbac a"], ["a.b", "."], ["a<b", "<"], ["x&y", "&"],
              ["Alice Cooper", "alice cooper"]]
            .map(([t, q]) => { const d = document.createElement("div"); d.innerHTML = hl(t, q);
              return [t, q, d.textContent, [...d.querySelectorAll("mark")].map((m) => m.textContent)]; })""")
        for text, q, rendered, marks in cases:
            assert rendered == text, (text, q, rendered)
            terms = q.lower().split()
            # a term the raw text carries is marked; one it does not ("a" in "Smith & Wesson" — the head's only
            # `a` was the entity's) is not
            assert bool(marks) == any(t in text.lower() for t in terms), (text, q, marks)
            for m in marks:
                assert m.lower() in terms, (text, q, marks)

    def test_overlapping_terms_mark_the_union_without_nesting(self, dash):
        """Pass 2 (Codex): "ab bc" on "abc" marked "ab" only; every occurrence, overlapping ones included, is
        marked as one merged range, never nested — and two terms that do not overlap ("ice coo" on
        "alice cooper", a space between them) stay two marks with the gap unmarked."""
        got = dash.evaluate("""() => [["abc", "ab bc"], ["aaa", "aa"], ["alice cooper", "ice coo"]].map(([text, query]) => {
            const node = document.createElement("div"); node.innerHTML = hl(text, query);
            return {text: node.textContent, html: node.innerHTML, nested: !!node.querySelector("mark mark")}; })""")
        assert got == [{"text": "abc", "html": "<mark>abc</mark>", "nested": False},
                       {"text": "aaa", "html": "<mark>aaa</mark>", "nested": False},
                       {"text": "alice cooper", "html": "al<mark>ice</mark> <mark>coo</mark>per", "nested": False}], got

    def test_a_name_with_an_ampersand_survives_the_first_keystroke(self, page, server):
        """A seeded name on the page itself: the users payload gains one person whose display name carries
        an ampersand; the first keystroke (`a`) must paint the name, not its entity."""
        def with_sam(route):
            resp = route.fetch()
            body = resp.json()
            body["users"].append({"user_name": "sam", "full_name": "Smith & Wesson", "logged_in": True, "group_count": 0,
                                  "providers": ["ldap-local"], "first_login_at": None, "first_login_source": None,
                                  "last_login_at": None, "created_at": None})
            body["total"] += 1
            body["count"] += 1
            body["logged_in_total"] += 1
            route.fulfill(response=resp, json=body)
        page.route("**/users?limit=*", with_sam)
        page.goto(f"{server}/#page=lookup&cluster=crc-local")
        page.wait_for_selector(".door")
        page.fill("#f-lookup-search", "a")
        page.wait_for_selector("tr[data-user='sam']")
        assert page.locator("tr[data-user='sam'] td:nth-child(2)").inner_text() == "Smith & Wesson"
        page.fill("#f-lookup-search", "alice a")
        page.wait_for_selector("tr[data-user='alice']")
        assert page.locator("tr[data-user='alice'] td:first-child").inner_text() == "alice"

    # ── F3: the doors' lines ──
    def test_the_users_door_counts_logins_the_way_the_users_tab_does(self, page, server):
        """A manual account (`oc create user`) is a row and not a login; the Users tab's headline is
        logged_in_total, and the door's line must be the same number. The one refusal these lists have is
        the missing identity, and both doors say so in the same words."""
        page.goto(f"{server}/#page=lookup&cluster=crc-local")
        page.wait_for_selector(".door")
        lines = page.evaluate("""() => { data.users = {total: 2, logged_in_total: 1, truncated: false, never_logged_in_members: {count: 3, names: []},
              users: [{user_name: "logged", logged_in: true}, {user_name: "made-by-hand", logged_in: false}]};
            data.namespaces = {forbidden: true}; render();
            return [...document.querySelectorAll(".door")].map((d) => [d.dataset.page, d.querySelector(".value").textContent.trim(), d.querySelector(".filterbar-note").textContent.trim()]); }""")
        by = {p: (v, line) for p, v, line in lines}
        assert by["users"] == ("2", "1 have logged in · 3 synced members never have"), by["users"]
        assert by["nsaudit"][1] == "needs an authenticated identity", by["nsaudit"]

    # ── F4: the self tier ──
    def test_the_lookup_says_when_its_counts_are_the_readers_own(self, page, scoped_server):
        p = _open_as(page, scoped_server, "alice")
        p.evaluate("() => { location.hash = '#page=lookup&cluster=crc-local'; }")
        p.wait_for_selector(".door")
        p.wait_for_function("() => data.groupsMeta && data.groupsMeta.scope === 'self'")
        assert p.locator("#main .scope-banner").count() == 1
        assert "alice" in p.locator("#main .scope-banner").inner_text()
        p.fill("#f-lookup-search", "a")
        p.wait_for_selector("#main h3")
        assert p.locator("#main .scope-banner").count() == 1
        # page-level, as _open_as set it: a page header outranks a context header
        p.set_extra_http_headers({"X-Forwarded-User": "root"})
        p.evaluate("() => refresh()")
        p.wait_for_function("() => data.groupsMeta && data.groupsMeta.scope === 'all'")
        assert p.locator("#main .scope-banner").count() == 0

    # ── F5: the empty state on a cluster with nothing recorded ──
    def test_the_empty_state_does_not_claim_data_a_cluster_does_not_have(self, page, server):
        page.goto(f"{server}/#page=lookup&cluster=prod-east")
        page.wait_for_selector(".door")
        page.wait_for_function("() => [...document.querySelectorAll('.door .value')].every(v => v.textContent.trim() !== '…')")
        page.fill("#f-lookup-search", "alice")
        page.wait_for_selector("#main .empty-note")
        note = page.locator("#main .empty-note").inner_text()
        assert "The data is not empty" not in note, note
        assert "nothing to search yet" in note, note

    # ── F6 / L8: one groups slot, its state recorded ──
    def test_the_groups_tab_never_paints_the_lookups_slice_under_a_filter(self, dash):
        dash.click("#tab-groups")
        dash.wait_for_selector("tr[data-group]")
        dash.select_option("#f-state", "empty")
        dash.wait_for_function("() => document.querySelectorAll('tr[data-group]').length === 2")
        dash.evaluate("() => { location.hash = '#page=lookup&cluster=crc-local'; }")
        dash.wait_for_selector(".door")
        dash.wait_for_function("() => data.groups && data.groups.length === 4")
        # render() is synchronous and refresh() is not: what this returns is the frame the tab handler paints
        first = dash.evaluate("""() => { document.getElementById('tab-groups').click();
            return {rows: document.querySelectorAll('tr[data-group]').length, select: document.getElementById('f-state').value,
                    loading: !!document.querySelector('#main .empty-note') && /Loading/.test(document.querySelector('#main .empty-note').textContent)}; }""")
        assert first == {"rows": 0, "select": "empty", "loading": True}, first
        dash.wait_for_function("() => document.querySelectorAll('tr[data-group]').length === 2")

    def test_the_also_line_never_counts_a_filtered_groups_slice(self, dash):
        dash.click("#tab-groups")
        dash.wait_for_selector("tr[data-group]")
        dash.select_option("#f-state", "empty")
        dash.wait_for_function("() => document.querySelectorAll('tr[data-group]').length === 2")
        dash.click("#tab-users")
        dash.wait_for_selector("tr[data-user]")
        dash.fill("#f-user-search", "rbac")
        dash.wait_for_selector("[data-widen]")
        line = dash.locator("[data-widen]").locator("xpath=..").inner_text()
        assert "group" not in line and "search everything for rbac" in line, line

    # ── F7: the keyboard ──
    def test_a_door_and_every_hit_answer_the_keyboard(self, page, server):
        page.goto(f"{server}/#page=lookup&cluster=crc-local")
        page.wait_for_selector(".door")
        page.focus(".door[data-page='groups'] button.drill")
        page.keyboard.press("Enter")
        page.wait_for_function("() => view.page === 'groups'", timeout=3_000)
        page.go_back()
        page.wait_for_selector(".door")
        page.fill("#f-lookup-search", "rbac alpha")
        page.wait_for_selector("tr[data-group='app-ocp-rbac-alpha-ns-admin'] button.drill")
        page.focus("tr[data-group='app-ocp-rbac-alpha-ns-admin'] button.drill")
        page.keyboard.press("Enter")
        page.wait_for_function("() => view.group === 'app-ocp-rbac-alpha-ns-admin'", timeout=3_000)
        page.go_back()
        page.wait_for_function("() => view.page === 'lookup'")
        page.fill("#f-lookup-search", "demo")
        page.wait_for_selector("tr[data-ns='prod-ns'] button.drill")
        page.focus("tr[data-ns='prod-ns'] button.drill")
        page.keyboard.press("Space")
        page.wait_for_function("() => view.ns === 'prod-ns'", timeout=3_000)
        page.go_back()
        page.wait_for_function("() => view.page === 'lookup'")
        page.fill("#f-lookup-search", "alice")
        page.wait_for_selector("tr[data-user='alice'] button.drill")
        page.focus("tr[data-user='alice'] button.drill")
        page.keyboard.press("Enter")
        page.wait_for_function("() => view.user === 'alice'", timeout=3_000)

    def test_a_group_drill_on_access_granted_answers_enter(self, dash):
        """Pre-existing: the shim swallowed Enter on every .drill without a user target — the group drills
        of Access granted included — and #174 added three more surfaces to the same handler."""
        dash.click('button.tab:text-is("Access granted")')
        dash.wait_for_selector("#main button.drill[data-group='was-managed']")
        dash.focus("#main button.drill[data-group='was-managed']")
        dash.keyboard.press("Enter")
        dash.wait_for_function("() => view.group === 'was-managed'", timeout=3_000)

    # ── Grok 6: the cut's door carries the query ──
    def test_open_the_full_list_carries_the_query_to_that_lists_box(self, dash):
        dash.evaluate("""() => { view.page = 'lookup'; view.lookupSearch = 'grp';
            data.groups = Array.from({length: 14}, (_, i) => ({name: 'grp-' + i, member_count: 0, sync_provider: null, binding_count: 0}));
            data.groupsMeta = {scope: 'all', viewer: null, state: 'all'};
            data.users = {users: [], total: 0}; data.namespaces = {namespaces: [], label_keys: []}; render(); }""")
        assert "2 more" in dash.locator("#main .filterbar-note", has_text="more").inner_text()
        dash.locator("#main button[data-page='groups'].linkish").click()
        # the position flips at once; the bar is repainted for the new page by the refresh that follows —
        # wait for the Groups tab's own box, not for view.page (CI's runner read a bar not yet rebuilt)
        dash.wait_for_selector("#f-group-search")
        assert dash.evaluate("() => [view.page, view.groupSearch, document.getElementById('f-group-search').value]") == ["groups", "grp", "grp"]

    # ── F8: the mark keeps the text's contrast ──
    def test_the_mark_keeps_the_text_above_the_contrast_bar(self, page, server):
        """The drill's link colour sits at 4.55:1 on the card; the accent wash behind a mark measured 3.40:1
        (light) and 3.74:1 (dark). Measured, not asserted from the sheet: the mark's composed background under
        its text, in both themes."""
        contrast = """() => {
          const parse = (s) => { let m = s.match(/rgba?\\(([\\d.]+),\\s*([\\d.]+),\\s*([\\d.]+)(?:,\\s*([\\d.]+))?\\)/);
            if (m) return [+m[1]/255, +m[2]/255, +m[3]/255, m[4] === undefined ? 1 : +m[4]];
            m = s.match(/color\\(srgb ([\\d.]+) ([\\d.]+) ([\\d.]+)(?: \\/ ([\\d.]+))?\\)/);
            return [+m[1], +m[2], +m[3], m[4] === undefined ? 1 : +m[4]]; };
          const lum = ([r, g, b]) => { const f = (c) => c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
          const over = (fg, bg) => [0, 1, 2].map((i) => fg[i] * fg[3] + bg[i] * (1 - fg[3])).concat([1]);
          const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
          return [...document.querySelectorAll('#main mark')].map((mark) => { const cs = getComputedStyle(mark);
            const card = over(parse(getComputedStyle(mark.closest('.card')).backgroundColor), parse(getComputedStyle(document.body).backgroundColor));
            return +ratio(parse(cs.color), over(parse(cs.backgroundColor), card)).toFixed(2); });
        }"""
        page.goto(f"{server}/#page=lookup&cluster=crc-local")
        page.wait_for_selector(".door")
        page.fill("#f-lookup-search", "alice")
        page.wait_for_selector("tr[data-user='alice'] mark")
        for theme in ("light", "dark"):
            page.evaluate("(t) => document.documentElement.setAttribute('data-theme', t)", theme)
            ratios = page.evaluate(contrast)
            assert ratios and min(ratios) >= 4.5, (theme, ratios)

    def test_the_groups_hits_fit_a_phone_without_sideways_scroll(self, page, server):
        """Seen on CRC at 375 px: the Owner cell does not wrap, so it took the width and every group name
        broke at each hyphen into three lines while the table scrolled sideways inside `.scroll-x`. Under
        520 px the Owner column is hidden — the name keeps two lines at most and the table fits; at 1280 px
        the column is there (review of #174, pass 3, OB3)."""
        def crc_owner(route):
            resp = route.fetch()
            body = resp.json()
            for g in body["groups"]:
                if g["sync_provider"]:
                    g["sync_provider"] = "app-ocp-rbac-group-groupsync_ldap"
            route.fulfill(response=resp, json=body)
        page.route("**/groups?state=*", crc_owner)
        page.goto(f"{server}/#page=lookup&cluster=crc-local")
        page.wait_for_selector(".door")
        page.fill("#f-lookup-search", "rbac")
        page.wait_for_selector("tr[data-group='app-ocp-rbac-alpha-ns-admin']")
        measure = """() => { const tr = document.querySelector("tr[data-group='app-ocp-rbac-alpha-ns-admin']");
            const name = tr.querySelector('button.drill'); const wrap = tr.closest('.scroll-x');
            return {lines: Math.round(name.getBoundingClientRect().height / parseFloat(getComputedStyle(name).lineHeight)),
                    ownerShown: getComputedStyle(tr.querySelector('td:nth-child(2)')).display !== 'none',
                    scrolls: wrap.scrollWidth > wrap.clientWidth}; }"""
        wide = page.evaluate(measure)
        assert wide == {"lines": 1, "ownerShown": True, "scrolls": False}, wide
        page.set_viewport_size({"width": 375, "height": 740})
        page.wait_for_timeout(300)
        phone = page.evaluate(measure)
        assert phone["ownerShown"] is False and phone["scrolls"] is False and phone["lines"] <= 2, phone

    def test_the_lookup_holds_at_phone_width(self, page, server):
        page.goto(f"{server}/#page=lookup&cluster=crc-local")
        page.wait_for_selector(".door")
        page.set_viewport_size({"width": 375, "height": 740})
        page.wait_for_timeout(300)
        assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
        page.fill("#f-lookup-search", "a")
        page.wait_for_selector("h3")
        page.wait_for_timeout(300)
        assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")


@pytest.fixture(scope="module")
def slow_lookup_server(tmp_path_factory):
    """The seeded app with the lookup's namespace list answering a second late — the proxy path's latency,
    exaggerated, so a step that reads the page it is LEAVING is caught by the clock rather than by luck."""
    import asyncio

    class _Late:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http" and scope["path"].endswith("/namespaces"):
                await asyncio.sleep(1.0)
            await self.app(scope, receive, send)

    db = str(tmp_path_factory.mktemp("gsd-slow") / "ui.db")
    _seed(db)
    settings = Settings(
        clusters=[ClusterConfig("crc-local", "https://api.crc.testing:6443", token_env="X")],
        db_path=db, login_capture_enabled=True,
        namespace_metadata_labels=("company.net/mnemonic", "company.net/app-environment"),
        view_restrictions_enabled=False,
    )
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(_Late(build_app(settings, run_poller=False)), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(f"{base}/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        raise RuntimeError("slow dashboard server did not start")
    yield base
    srv.should_exit = True
    thread.join(timeout=5)


class TestTheWalksLookupStep:
    """The e2e walk's lookup step (e2e-walk/e2e_capture.py, `walk_lookup`), driven against the seed with the
    walk's own `Walk`: main() runs it after walk_tabs, so it starts on whatever tab the strip ends on, and it
    must capture the LOOKUP — never the page it is leaving, and never skip on a page whose bar holds a list's
    own box (review of #174, pass 3, OB3)."""

    @staticmethod
    def _walk(page, out):
        import importlib.util
        import pathlib
        path = pathlib.Path(__file__).resolve().parents[1] / "e2e-walk" / "e2e_capture.py"
        spec = importlib.util.spec_from_file_location("e2e_capture", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod, mod.Walk(page, out)

    def test_the_step_captures_the_lookup_and_not_the_tab_it_left(self, page, slow_lookup_server, tmp_path):
        """walk_tabs ends on Usage, whose off state is a `.empty-note` — the selector the step waited on — and
        the doors' "…" test over zero doors is vacuously true: with the lookup's fetch a second out, the first
        capture was of the Usage page and the step recorded "no matches" where the seed has two namespaces
        matching "demo", then skipped the namespace drill for want of a row."""
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        # #158 made Home the landing page; this test's subject is the walk step, and it needs a painted
        # page to start from, so it names the one it means rather than riding the default route.
        page.goto(f"{slow_lookup_server}/#page=overview")
        page.wait_for_selector(".hero .value", timeout=10_000)
        page.click('button.tab:text-is("Usage")')
        page.wait_for_selector('button.tab[aria-current="page"]:text-is("Usage")')
        page.wait_for_selector("#main .empty-note")
        mod, w = self._walk(page, tmp_path)
        mod.walk_lookup(w)
        by = {s["step"]: s for s in w.steps}
        assert "lookup demo" in by, [s["step"] for s in w.steps]
        assert by["lookup demo"]["ok"] and "Namespaces · 2 of 9" in by["lookup demo"]["detail"], by["lookup demo"]
        assert "lookup -> namespace page" in by and by["lookup -> namespace page"]["detail"] == "prod-ns", by
        assert by["lookup at 375 px"]["ok"], by["lookup at 375 px"]
        assert not w.errors and not errors, (w.errors, errors)

    def test_the_step_does_not_skip_from_a_list_page(self, dash, tmp_path):
        """A list page's bar holds that list's own box and no Find box; that is not "a build without the
        lookup", and a step that records itself skipped there is a pass that walked nothing."""
        dash.click("#tab-groups")
        dash.wait_for_selector("#f-group-search")
        mod, w = self._walk(dash, tmp_path)
        mod.walk_lookup(w)
        steps = [s["step"] for s in w.steps]
        assert "lookup demo" in steps, steps
        assert not any("skipped" in s["detail"] for s in w.steps), steps

def test_index_is_never_heuristically_cached(server):
    """Reported from the field: a deploy landed but the browser kept the old page, so a
    shipped fix looked like it was never shipped. Without Cache-Control, browsers apply
    heuristic caching to HTML — and this single file IS the whole app, so a stale shell
    silently disables every change behind it."""
    import httpx

    response = httpx.get(server + "/", timeout=10)
    cache = response.headers.get("cache-control", "")
    assert "no-cache" in cache, f"index served with Cache-Control: {cache!r}"


class TestClusterScopedNavigation:
    """Found adversarially: the trail stored page/groupsync/group/user but NOT cluster."""

    def test_switching_cluster_abandons_the_drilldown(self, dash):
        """Group names repeat across clusters, so carrying a drill-down across a switch
        re-requests that name against the new cluster — a different object under the same
        name, or a 404 error page."""
        dash.locator("button[data-nav='groups']").click()
        dash.wait_for_selector("tr[data-group]")
        dash.locator("tr[data-group='app-ocp-rbac-alpha-ns-admin']").click()
        dash.wait_for_selector("#back-groups")

        dash.select_option("#f-cluster", "prod-east")
        dash.wait_for_function("() => !document.querySelector('#back-groups')")
        body = dash.locator("body").inner_text()
        assert "Dashboard API error" not in body, "carried the drill-down into the new cluster"

    def test_back_restores_the_cluster_it_was_captured_with(self, dash):
        dash.locator("button[data-nav='groups']").click()
        dash.wait_for_selector("tr[data-group]")
        dash.locator("tr[data-group='app-ocp-rbac-alpha-ns-admin']").click()
        dash.wait_for_selector("#back-groups")
        dash.locator("tr[data-user='alice']").click()
        dash.wait_for_selector("text=Group memberships")

        # The position we would go BACK to now lives on the history entry itself, which is
        # what makes the label correct after a Forward too. Same guarantee, real mechanism.
        assert dash.evaluate("() => history.state.from.cluster") == "crc-local"
        dash.locator("#back-groups").click()
        dash.wait_for_selector("text=Membership changes")
        assert dash.evaluate("() => view.cluster") == "crc-local"


class TestBrowserHistory:
    """The browser's own Back and Forward, which used to leave the dashboard entirely.

    Navigation lived in a private `trail` array and nothing was in the URL, so Back went to
    whatever page preceded the dashboard and the reader lost their position — worst on the
    drill-downs, which are exactly where somebody has spent effort getting to.

    ONE STACK is the property under test here. The in-page button now calls history.back(),
    so both buttons walk the same list; two stacks would diverge the moment anyone mixed them.
    """

    def _drill(self, dash):
        dash.locator("button[data-nav='groups']").click()
        dash.wait_for_selector("tr[data-group]")
        dash.locator("tr[data-group='app-ocp-rbac-alpha-ns-admin']").click()
        dash.wait_for_selector("#back-groups")

    def test_the_url_carries_the_position(self, dash):
        """Without this nothing else is possible: Back needs somewhere to go back TO."""
        self._drill(dash)
        assert "page=groups" in dash.url
        assert "group=app-ocp-rbac-alpha-ns-admin" in dash.url

    def test_browser_back_leaves_a_drilldown_without_leaving_the_dashboard(self, dash):
        self._drill(dash)
        dash.go_back()
        dash.wait_for_function("() => !document.querySelector('#back-groups')")
        assert "group=" not in dash.url
        assert dash.locator("tbody tr").count() == SYNCED_GROUPS, "did not return to the group list"

    def test_browser_back_retraces_tab_switches(self, dash):
        """The biggest gap in the old design: tab clicks pushed nothing and CLEARED the trail,
        so every page but the current one was unreachable backwards."""
        dash.locator("button[data-nav='groups']").click()
        dash.wait_for_selector("tr[data-group]")
        dash.locator("button[data-nav='usage']").click()
        dash.wait_for_function("() => document.body.dataset.page === 'usage'")
        dash.go_back()
        dash.wait_for_function("() => document.body.dataset.page === 'groups'")
        assert "page=groups" in dash.url

    def test_browser_forward_returns_to_where_back_came_from(self, dash):
        self._drill(dash)
        dash.go_back()
        dash.wait_for_function("() => !document.querySelector('#back-groups')")
        dash.go_forward()
        dash.wait_for_selector("#back-groups")
        assert "group=app-ocp-rbac-alpha-ns-admin" in dash.url

    def test_the_in_page_button_and_the_browser_button_share_one_stack(self, dash):
        """Mixed use is the case two stacks get wrong: in-page Back, then browser Back."""
        self._drill(dash)
        dash.locator("tr[data-user='alice']").click()
        dash.wait_for_selector("text=Group memberships")

        dash.locator("#back-groups").click()          # in-page: user -> group
        dash.wait_for_selector("text=Membership changes")
        assert "group=app-ocp-rbac-alpha-ns-admin" in dash.url

        dash.go_back()                                 # browser: group -> list
        dash.wait_for_function("() => !document.querySelector('#back-groups')")
        assert dash.locator("tbody tr").count() == SYNCED_GROUPS

    def test_a_pasted_link_opens_at_that_position(self, dash):
        """The other half of putting position in the URL: it has to be shareable."""
        dash.goto(dash.url.split("#")[0] + "#page=groups&cluster=crc-local"
                  + "&group=app-ocp-rbac-alpha-ns-admin")
        dash.wait_for_selector("text=Membership changes")
        assert "app-ocp-rbac-alpha-ns-admin" in dash.locator("h2").first.inner_text()

    def test_arriving_by_link_still_offers_a_way_out(self, dash):
        """A pasted drill-down has no `from`, so history.back() would leave the dashboard.

        The button rises to the natural parent instead — a position the reader can then Back
        out of normally. Verified by asserting we are still ON the dashboard afterwards.
        """
        dash.goto(dash.url.split("#")[0] + "#page=groups&cluster=crc-local"
                  + "&group=app-ocp-rbac-alpha-ns-admin")
        dash.wait_for_selector("#back-groups")
        assert dash.evaluate("() => history.state.from") is None, "expected no back target"
        dash.locator("#back-groups").click()
        dash.wait_for_function("() => !document.querySelector('#back-groups')")
        assert dash.locator("tbody tr").count() == SYNCED_GROUPS, "left the dashboard instead of rising"

    def test_a_crafted_hash_cannot_execute_script(self, dash):
        """The one security regression this feature introduced, and its guard.

        The sink is old — backLabel() is written into innerHTML by four callers — but before this
        branch no URL text could reach `view`, so those names were always cluster data. Putting
        position in the URL made them attacker-chosen: one emailed link plus one ordinary click
        ran script in the reader's session, behind the oauth-proxy, with access to every endpoint.
        """
        payload = "<img src=x onerror=window.__pwned=1>"
        dash.goto(dash.url.split("#")[0] + "#page=groups&cluster=crc-local&groupsync="
                  + urllib.parse.quote(payload))
        dash.reload()
        dash.wait_for_selector("#f-state")
        dash.locator("tr[data-group='app-ocp-rbac-alpha-ns-admin']").click()
        dash.wait_for_selector("#back-groups")
        assert dash.evaluate("() => window.__pwned || 0") == 0, "crafted hash executed script"
        assert dash.locator(".back img").count() == 0, "hash markup was parsed as HTML"
        assert payload in dash.locator("#back-groups").inner_text(), (
            "the payload should still be VISIBLE as text — escaped, not silently dropped"
        )

    def test_a_link_opened_in_a_fresh_tab_boots_at_that_position(self, dash):
        """Distinct from the pasted-into-this-tab test, and the distinction is the whole point.

        `page.goto(url + '#hash')` on an already-loaded page is a SAME-DOCUMENT navigation — the
        document survives, so boot never re-runs and only the hashchange path is exercised. A
        genuinely shared link opens in a new tab and goes through boot. reload() forces that, and
        without it this behaviour could regress with a fully green suite.
        """
        dash.goto(dash.url.split("#")[0] + "#page=groups&cluster=crc-local"
                  + "&group=app-ocp-rbac-alpha-ns-admin")
        dash.reload()
        dash.wait_for_selector("text=Membership changes")
        assert dash.evaluate("() => view.page") == "groups"
        assert "app-ocp-rbac-alpha-ns-admin" in dash.locator("h2").first.inner_text()

    def test_the_boot_entry_carries_the_default_cluster(self, dash):
        """The default cluster is not known until the cluster list arrives — after boot stamped
        the entry — so the first entry used to carry no cluster at all, and Back from the reader's
        FIRST cluster switch restored a drill-down against the wrong one. Measured on a tab that
        needs a cluster: on the Overview an absent cluster is the fleet view (#172), so the boot
        entry there carries none, by design."""
        assert dash.evaluate("() => history.state.pos.cluster") is None, "the Overview boots into the fleet"
        dash.click("#tab-groups")
        dash.wait_for_function("() => view.cluster")
        assert dash.evaluate("() => history.state.pos.cluster") == "crc-local"

    def test_the_skip_link_does_not_navigate(self, dash):
        """"Skip to main content" is `#main`: a hash carrying none of the position keys. Treating
        it as a position reset the reader to Overview — the accessibility affordance throwing them
        off the page they were reading."""
        self._drill(dash)
        dash.evaluate("() => { location.hash = 'main'; }")
        dash.wait_for_timeout(400)
        assert dash.evaluate("() => view.page") == "groups"
        assert dash.evaluate("() => view.group") == "app-ocp-rbac-alpha-ns-admin"

    def test_a_reload_keeps_the_back_target(self, dash):
        """F5 is what a reader presses when a page looks stale. Chromium preserves history.state
        across it, and boot used to clobber `from` with null — after which the in-page button rose
        to the parent while the browser's Back went one entry further."""
        self._drill(dash)
        dash.locator("tr[data-user='alice']").click()
        dash.wait_for_selector("text=Group memberships")
        dash.reload()
        dash.wait_for_selector("#back-groups")
        assert dash.evaluate("() => history.state.from && history.state.from.group") == \
            "app-ocp-rbac-alpha-ns-admin"
        assert "app-ocp-rbac-alpha-ns-admin" in dash.locator("#back-groups").inner_text()

    def test_reselecting_the_same_tab_does_not_stack_an_entry(self, dash):
        """An identical position replaced rather than pushed: two duplicate entries made Back
        appear to do nothing, and could leave it oscillating instead of leaving."""
        dash.locator("button[data-nav='groups']").click()
        dash.wait_for_selector("tr[data-group]")
        before = dash.evaluate("() => history.length")
        dash.locator("button[data-nav='groups']").click()
        dash.locator("button[data-nav='groups']").click()
        dash.wait_for_timeout(300)
        assert dash.evaluate("() => history.length") == before, "re-selecting a tab stacked entries"

    def test_the_label_is_still_right_after_a_forward(self, dash):
        """Claimed as the improvement over the old private stack, and previously asserted nowhere.
        `from` lives ON the entry, so Forward restores the label with it."""
        self._drill(dash)
        dash.locator("tr[data-user='alice']").click()
        dash.wait_for_selector("text=Group memberships")
        label = dash.locator("#back-groups").inner_text()
        dash.go_back()
        dash.wait_for_selector("text=Membership changes")
        dash.go_forward()
        dash.wait_for_selector("text=Group memberships")
        assert dash.locator("#back-groups").inner_text() == label

    def test_a_superseded_fetch_does_not_paint_the_wrong_page(self, dash):
        """Back is instant; a fetch is not. That gap is new — before this feature there was no
        instant way to leave a page mid-request.

        A group fetch that lands after the reader has moved on used to write `data.group` and call
        render(), which derives from the CURRENT view — so the first group's data appeared under the
        second group's position. The response is now DISCARDED rather than merely un-rendered:
        leaving it in `data` would surface on the next render that does not refetch, which is a
        sort click or the 30s poll.

        The fetch is HELD rather than delayed by a timer, and that is what makes this deterministic.
        Two earlier attempts were not: a Playwright route glob that never matched, and a version
        that pressed Back 10ms after the click — too early, because refresh() reads `view` at each
        await, so the drill's own refresh saw the position already reset and fetched the LIST. The
        request has to be in flight before the reader leaves, which is the only ordering that can
        strand a response.
        """
        SLOW = "/groups/app-ocp-rbac-alpha-ns-admin"
        dash.locator("button[data-nav='groups']").click()
        dash.wait_for_selector("tr[data-group]")
        dash.evaluate("""(slow) => {
            const orig = window.fetch;
            window.__release = null;
            window.__origFetch = orig;
            window.fetch = (u, o) => String(u).includes(slow)
              ? new Promise((res) => { window.__release = () => res(orig(u, o)); })
              : orig(u, o);
        }""", SLOW)
        try:
            dash.locator("tr[data-group='app-ocp-rbac-alpha-ns-admin']").click()
            # The held request is now in flight — this is the state the reader leaves from.
            dash.wait_for_function("() => window.__release !== null")

            dash.go_back()
            dash.wait_for_selector("#f-state")
            dash.locator("tr[data-group='app-ocp-rbac-abcd-ns-superuser']").click()
            dash.wait_for_selector("#back-groups")
            assert dash.evaluate("() => view.group") == "app-ocp-rbac-abcd-ns-superuser"

            dash.evaluate("() => window.__release()")   # the abandoned response lands
            dash.wait_for_timeout(600)

            assert dash.evaluate("() => view.group") == "app-ocp-rbac-abcd-ns-superuser"
            assert dash.evaluate("() => data.group && data.group.name") == \
                "app-ocp-rbac-abcd-ns-superuser", (
                "the abandoned fetch overwrote data.group — it would surface on the next repaint"
            )
            assert "app-ocp-rbac-alpha-ns-admin" not in dash.locator("body").inner_text(), (
                "the superseded group was painted over the position the reader is on"
            )
        finally:
            dash.evaluate("() => { if (window.__origFetch) window.fetch = window.__origFetch; }")

    def test_a_pasted_groupsync_link_labels_where_the_button_actually_goes(self, dash):
        """With no back target, goBack() rises to the PARENT of where we are. The label used to say
        "all groups" regardless — naming a page the button does not open, on a GroupSync detail."""
        dash.goto(dash.url.split("#")[0] + "#page=overview&cluster=crc-local"
                  + "&groupsync=ldap-groupsync")
        dash.reload()
        dash.wait_for_selector("#back")
        assert dash.evaluate("() => history.state.from") is None, "expected no back target"
        assert dash.locator("#back").inner_text().strip() == "← overview", (
            "the label must describe where goBack() rises to, not a fixed string"
        )
        dash.locator("#back").click()
        # The CR detail's parent is the cluster it lives under — #page=overview&cluster=crc-local, the
        # scoped view (#172), which carries its own back control to the fleet.
        dash.wait_for_function("() => !view.groupsync && document.querySelector('#back') && document.querySelector('#back').textContent.includes('all clusters')")
        assert dash.evaluate("() => [view.page, view.cluster, view.groupsync]") == ["overview", "crc-local", None]

    def test_back_after_a_cluster_switch_restores_that_cluster(self, dash):
        """Cluster is part of the position, not context around it — group names repeat."""
        self._drill(dash)
        dash.select_option("#f-cluster", "prod-east")
        dash.wait_for_function("() => view.cluster === 'prod-east'")
        dash.go_back()
        dash.wait_for_function("() => view.cluster === 'crc-local'")
        assert "cluster=crc-local" in dash.url


    def test_a_group_drill_inside_a_group_row_navigates_once(self, dash):
        """A user page's membership and history rows put a `data-group` button inside a `tr[data-group]`; the
        group handler, unlike the user handler, did not stop propagation, so one click — or Enter — navigated
        twice (a push, then a replace of the same position) and fetched twice (OB1's keyboard sweep, pass 3 of
        #167). Counted at the two chokepoints every drill goes through."""
        dash.locator("button[data-nav='users']").click()
        dash.wait_for_selector("tr[data-user='alice']")
        dash.locator("tr[data-user='alice'] button.drill").click()
        dash.wait_for_selector("h2:text-is('alice')")
        dash.evaluate("""() => { window.__n = {nav: 0, refresh: 0}; const n0 = navigate, r0 = refresh;
            navigate = function (...a) { __n.nav++; return n0.apply(this, a); };
            refresh = function (...a) { __n.refresh++; return r0.apply(this, a); }; }""")
        button = dash.locator("tr[data-group='app-ocp-rbac-alpha-ns-admin'] button.drill").first
        button.focus()
        button.press("Enter")
        dash.wait_for_selector("h2:text-is('app-ocp-rbac-alpha-ns-admin')")
        dash.wait_for_timeout(300)
        assert dash.evaluate("() => [__n.nav, __n.refresh]") == [1, 1]


class TestNamespaceAuditPage:
    """The Namespace-audit tab had no browser test at all.

    The `dash` fixture's pageerror guard covers the page as LOADED; a renderer that throws
    only when its tab is opened is invisible to it. Proven by injecting
    `DELIBERATE_BREAKAGE_nsaudit();` at the top of `nsAuditPage()` — the whole suite still
    reported `431 passed, 4 skipped`. Same gap TestRbacPolicyPage below was written for,
    reopened for the two newest tabs.
    """

    def _open(self, dash):
        dash.click('button.tab:text-is("Namespace audit")')
        dash.wait_for_selector("h2:text-is('Namespace audit')")

    def test_the_page_renders_without_a_javascript_error(self, dash):
        errors = []
        dash.on("pageerror", lambda e: errors.append(str(e)))
        self._open(dash)
        assert not errors, errors
        assert "Dashboard API error" not in dash.locator("body").inner_text()

    def test_people_exposed_counts_people(self, dash):
        """Both ways this number has been wrong, in one assertion.

        Summing per-namespace `distinct_users` counts jdoe once per namespace and says 3.
        Splitting the rollup's user list on a comma turns one LDAP DN into four and says 5.
        The seed holds two people, so the answer is 2.
        """
        self._open(dash)
        kpi = dash.locator(".kpi", has_text="People exposed").first
        assert kpi.locator(".value").inner_text().strip() == "2"

    def test_a_dn_username_stays_one_person(self, dash):
        """A user name can be an LDAP DN. Rendering the rollup's user list by splitting a
        comma-delimited string showed that one person as four names in this cell, beside a
        People column that said 1."""
        self._open(dash)
        who = dash.locator("td.who").all_inner_texts()
        assert any("cn=jdoe,ou=people,dc=ephico2real,dc=com" in w for w in who), who

    def test_grants_to_migrate_is_the_cluster_not_the_page(self, dash):
        """Three non-platform grants seeded; kubeadmin is excluded and counted separately."""
        self._open(dash)
        kpi = dash.locator(".kpi", has_text="Grants to migrate").first
        assert kpi.locator(".value").inner_text().strip() == "3"


class TestUsagePage:
    """The Usage tab had no browser test either, and was broken in the default config.

    Proven the same way: `DELIBERATE_BREAKAGE_usage();` at the top of `usagePage()` left the
    suite at `431 passed, 4 skipped`.
    """

    def _open(self, dash):
        dash.click('button.tab:text-is("Usage")')
        dash.wait_for_selector("h2:text-is('Dashboard usage')")

    def test_the_page_renders_without_a_javascript_error(self, dash):
        errors = []
        dash.on("pageerror", lambda e: errors.append(str(e)))
        self._open(dash)
        assert not errors, errors

    def test_proxy_off_explains_itself_instead_of_erroring(self, dash):
        """With the proxy off the endpoint 403s BY DESIGN — there is no authenticated
        identity to scope personnel data to. The tab rendered that as "Dashboard API error:
        403 Forbidden" with no way back, and the panel written to explain exactly this could
        never appear, because api() threw before `data.usage` was ever assigned."""
        self._open(dash)
        body = dash.locator("body").inner_text()
        assert "Dashboard API error" not in body, body[:300]
        assert "Not being recorded" in body
        assert "oauthProxy.enabled=true" in body


class TestRbacPolicyPage:
    def test_the_policy_heading_is_a_direct_card_child_with_its_accent_rail(self, dash):
        """Pass 2 (Grok V4): the plain card's heading is the old markup exactly — a direct child of the card —
        and the accent rail every card heading wears applies to it."""
        self._open(dash)
        dash.wait_for_selector("h3:has-text('Policy operator')")
        got = dash.evaluate("""() => { const h = [...document.querySelectorAll('#main h3')].find(e => e.textContent.includes('Policy operator'));
            return {parent: h.parentElement.className, width: getComputedStyle(h, '::before').width}; }""")
        assert "row-wrap" not in got["parent"] and got["width"] == "3px", got

    def test_the_shared_policy_card_changes_only_the_failing_consequence(self, dash):
        """#172 shares the fleet's policy card with this tab and promised it only the consequence line; the
        shared card had also moved the failing row first, added the count to the heading, the attention wash
        and the state cell (Codex F5, OB1 O10). This tab's card is the pre-#172 card plus the line."""
        self._open(dash)
        dash.wait_for_selector("h3:has-text('Policy operator')")
        card = dash.locator("section.card", has=dash.locator("h3", has_text="Policy operator (NamespaceConfig / GroupConfig)"))
        assert card.locator("h3").inner_text().strip() == "Policy operator (NamespaceConfig / GroupConfig)"
        assert card.locator("tbody code").all_inner_texts() == ["cluster-admin-groupconfig-rbac", "multitenant"], "the seed's order"
        failing = card.locator("tbody tr", has_text="multitenant")
        assert failing.get_attribute("class") in (None, "")
        assert failing.locator("td.state-cell").count() == 0
        assert "reconcile error" in failing.inner_text()
        assert "RBAC has quietly stopped reconciling" in failing.inner_text()
        assert "failed calling webhook validate.kyverno.svc-fail" in card.inner_text()

    """The RBAC-policy tab. It shipped broken — `section is not defined`, because the
    renderer was local to bindingsPage() — and the suite did not notice, because nothing
    opened the tab. Every page needs at least one test that renders it."""

    def _open(self, dash):
        dash.click('button.tab:text-is("RBAC policy")')
        dash.wait_for_selector("h2:text-is('RBAC policy')")

    def test_the_page_renders_without_a_javascript_error(self, dash):
        errors = []
        dash.on("pageerror", lambda e: errors.append(str(e)))
        self._open(dash)
        body = dash.locator("body").inner_text()
        assert "Dashboard API error" not in body, body[:300]
        assert not errors, errors

    def test_it_reports_the_policy_operator_and_the_unmanaged_set(self, dash):
        self._open(dash)
        # The tab paints first and fetches after; the operator card lands with the fetch. Before #172 the
        # Overview had prefetched it for the selected cluster — the fleet view has no selected cluster.
        dash.wait_for_selector("h3:has-text('Policy operator')")
        body = dash.locator("body").inner_text()
        assert "Policy operator" in body
        assert "outside the policy system" in body

    def test_the_tab_is_marked_current(self, dash):
        self._open(dash)
        current = dash.locator('button.tab[aria-current="page"]').inner_text()
        assert current.strip() == "RBAC policy"


class TestLoginsPage:
    """The Logins tab: who tried to sign in to the cluster, and what happened.

    Every assertion here is about a way the page could MISLEAD rather than about how it looks.
    The record is a window — login lines exist only while the authentication operator is at
    Debug, and a pod's log dies with the pod — so the one failure mode that matters is a page
    that lets an empty or partial record read as "nobody signed in".
    """

    def _open(self, dash):
        dash.click('button.tab:text-is("Logins")')
        dash.wait_for_selector("h2:text-is('Login attempts')")

    def test_the_page_renders_without_a_javascript_error(self, dash):
        errors = []
        dash.on("pageerror", lambda e: errors.append(str(e)))
        self._open(dash)
        body = dash.locator("body").inner_text()
        assert "Dashboard API error" not in body, body[:300]
        assert not errors, errors

    def test_the_tab_is_marked_current_and_owns_its_accent(self, dash):
        self._open(dash)
        assert dash.locator('button.tab[aria-current="page"]').inner_text().strip() == "Logins"
        # The accent drives the tab bar, the card edge and the hero numeral. If the token were
        # missing the whole page would silently fall back to the previous section's colour.
        assert dash.locator("body").get_attribute("data-page") == "logins"
        accent = dash.evaluate(
            "() => getComputedStyle(document.body).getPropertyValue('--accent').trim()")
        logins = dash.evaluate(
            "() => getComputedStyle(document.body).getPropertyValue('--tab-logins').trim()")
        assert accent and accent == logins, f"accent {accent!r} != --tab-logins {logins!r}"

    def test_every_attempt_is_listed_with_its_outcome(self, dash):
        self._open(dash)
        body = dash.locator("body").inner_text()
        for who in ("alice", "bob", "mallory", "developer"):
            assert who in body, f"{who} is missing from the attempt list"
        # The parser's outcome, restated for a reader. "LDAP Result Code 49" is what the log
        # carries and it explains nothing, so the page must not be showing only that.
        assert "wrong password" in body
        assert "account locked" in body
        assert "signed in" in body

    def test_the_window_is_stated_on_screen_in_both_directions(self, dash):
        """The load-bearing one. An empty or partial record must never read as a clean bill.

        Both edges are data: `capture_started_at` is when watching began, `retained_since` is
        the oldest attempt still kept. The page has to say both, and has to say that nothing
        before the first was ever written down.
        """
        self._open(dash)
        body = dash.locator("body").inner_text()
        assert "Watching since" in body
        assert "oldest attempt still retained" in body
        assert "last read" in body
        assert "nothing was" in body and "observed" in body, (
            "the page does not say that an empty list means nothing was OBSERVED — without "
            "that sentence a reader takes silence for proof that nobody signed in"
        )

    def test_it_explains_a_record_that_reaches_behind_its_own_start(self, dash):
        """capture_started_at can be LATER than retained_since, and it looks like a bug.

        The first read looks back an hour, so it returns attempts older than the moment
        watching began. The seed puts the first read 20 minutes ago with attempts before it.
        """
        self._open(dash)
        assert "predates the first read" in dash.locator("body").inner_text()

    def test_the_ungoverned_accounts_come_before_the_chronology(self, dash):
        """A finding buried in 200 time-ordered rows is a finding nobody reads."""
        self._open(dash)
        headings = dash.locator("section.card h2, section.card h3").all_inner_texts()
        headings = [h.strip() for h in headings]
        assert "Accounts in no synced group" in headings, headings
        assert headings.index("Accounts in no synced group") < headings.index("Every attempt"), (
            f"the finding is below the chronology: {headings}"
        )

    def test_it_separates_a_removed_account_from_one_never_governed(self, dash):
        """The two reasons a name is ungoverned are different problems with different owners.

        bob was removed from every group and is still trying — an offboarding that did not
        finish. mallory has never been in one. Both are `known_user: false`; only the timeline
        tells them apart, and the page has to show which.
        """
        self._open(dash)
        card = dash.locator("section.card", has=dash.locator(
            "h3:text-is('Accounts in no synced group')"))
        bob = card.locator("tbody tr").filter(has_text="bob").inner_text()
        assert "was, and no longer is" in bob, bob
        mallory = card.locator("tbody tr").filter(has_text="mallory").inner_text()
        assert "never" in mallory, mallory
        assert "was, and no longer is" not in mallory, (
            "a name nobody ever governed is being reported as an unfinished offboarding"
        )

    def test_a_governed_member_is_not_reported_as_a_finding(self, dash):
        """alice is in a synced group. Reporting her would make the list noise."""
        self._open(dash)
        rows = dash.locator("section.card", has=dash.locator(
            "h3:text-is('Accounts in no synced group')")).locator("tbody tr")
        assert "alice" not in str(rows.all_inner_texts()), rows.all_inner_texts()

    def test_a_break_glass_success_is_labelled_and_excluded(self, dash):
        """`developer` is a local HTPasswd account, not a person to offboard.

        It has to be visible in the chronology — a break-glass login is worth seeing — and out
        of the finding list, because there is nowhere to migrate it to.
        """
        self._open(dash)
        chronology = dash.locator("section.card", has=dash.locator(
            "h3:text-is('Every attempt')"))
        row = chronology.locator("tbody tr").filter(has_text="developer").first
        assert "break-glass" in row.inner_text(), (
            "a SUCCESS on a local provider is a break-glass sign-in and must say so"
        )
        rows = dash.locator("section.card", has=dash.locator(
            "h3:text-is('Accounts in no synced group')")).locator("tbody tr")
        assert "developer" not in rows.all_inner_texts().__str__(), rows.all_inner_texts()
        # And the count beside the list agrees with the list: bob and mallory, not developer.
        hero = dash.locator(".hero .value").first.inner_text().strip()
        assert hero == "2", f"hero says {hero}, expected the 2 ungoverned accounts"

    def test_a_failed_local_provider_attempt_is_not_called_break_glass(self, dash):
        """Seen on the live cluster as `testuser break-glass`, which asserted something false.

        A failed attempt against the HTPasswd provider says WHICH PROVIDER was tried and nothing
        about the account — HTPasswd reports no reason, so the name may not exist at all. Calling that
        row break-glass claims it is a break-glass account.
        """
        self._open(dash)
        chronology = dash.locator("section.card", has=dash.locator(
            "h3:text-is('Every attempt')"))
        # Seed a failure on the local provider by filtering to it is not possible — the fixture's
        # break-glass row is a success — so assert the RULE instead: no failed row wears the label.
        for i in range(chronology.locator("tbody tr").count()):
            row = chronology.locator("tbody tr").nth(i).inner_text()
            if "break-glass" in row:
                assert "signed in" in row, (
                    f"a non-success row is labelled break-glass: {row!r}"
                )

    def test_a_name_with_no_history_is_not_a_link_into_an_error(self, dash):
        """/users/{name} 404s for a name with no groups AND no history — which is mallory.

        Making every username a link would send the reader from the most interesting row on the
        page straight into an error card, so the affordance is offered only where it leads
        somewhere. bob has a timeline, so bob IS a link.
        """
        self._open(dash)
        assert dash.locator('button.drill[data-user="mallory"]').count() == 0, (
            "mallory is drillable, and her user page 404s"
        )
        assert dash.locator('button.drill[data-user="bob"]').count() >= 1, (
            "bob has membership history, so his removal is worth drilling into"
        )

    def test_drilling_a_user_opens_the_user_page_and_back_returns_here(self, dash):
        """The drill goes through navigate(), so one history stack serves both buttons.

        This is also the regression test for a drill that set the URL and rendered nothing:
        every drill-down renders under page=groups, so the handler has to name that page.
        """
        self._open(dash)
        dash.locator('button.drill[data-user="bob"]').first.click()
        dash.wait_for_selector("#back-groups")
        assert dash.evaluate("() => view.page") == "groups"
        assert dash.evaluate("() => view.user") == "bob"
        assert "page=groups" in dash.url and "user=bob" in dash.url
        # The label has to name the page the button actually opens.
        assert dash.locator("#back-groups").inner_text().strip() == "← logins"
        dash.locator("#back-groups").click()
        dash.wait_for_selector("h2:text-is('Login attempts')")
        assert dash.evaluate("() => view.page") == "logins"

    def test_the_outcome_filter_narrows_the_list_without_moving_the_totals(self, dash):
        """`summary` describes the whole record; the table is one filtered page of it.

        A header that moved with the filter would make every number on the page mean
        "whatever is currently selected", which is not a number anyone can act on.
        """
        self._open(dash)
        before = dash.locator(".kpi", has_text="Attempts").inner_text()
        dash.select_option("#f-outcome", "success")
        dash.wait_for_function("() => view.loginOutcome === 'success'")
        dash.wait_for_selector(".chip:text-is('filtered to signed in')")
        rows = dash.locator("section.card", has=dash.locator(
            "h3:text-is('Every attempt')")).locator("tbody tr")
        assert rows.count() == 2, rows.all_inner_texts()
        assert dash.locator(".kpi", has_text="Attempts").inner_text() == before, (
            "the whole-record counts moved with the filter"
        )

    def test_the_filter_offers_only_outcomes_that_exist(self, dash):
        """A cluster on OpenLDAP can never produce the AD sub-code outcomes.

        Offering all ten would invite the reader to filter to a guaranteed-empty table and draw
        a conclusion from it.
        """
        self._open(dash)
        values = dash.locator("#f-outcome option").evaluate_all(
            "els => els.map(e => e.value)")
        assert values[0] == "all"
        assert set(values[1:]) == {"success", "bad_password", "rejected", "account_locked"}, values

    def test_the_detail_column_carries_the_directory_diagnostic(self, dash):
        """The result code is not the cause: AD returns 49 for expired, locked and disabled
        alike, and only the `data <hex>` sub-code in the diagnostic separates them."""
        self._open(dash)
        body = dash.locator("body").inner_text()
        assert "775" in body, "the AD sub-code that explains the lock is not shown"
        assert "LDAP 49" in body

    def test_the_cluster_selector_stays_because_this_page_is_cluster_scoped(self, dash):
        """Unlike Usage. These are logins to a CLUSTER, so hiding the selector would claim a
        scope the page does not have — and the title has to name the cluster too."""
        self._open(dash)
        assert dash.locator("#f-cluster").count() == 1
        assert "crc-local" in dash.locator("#scope-note").inner_text()


@pytest.fixture(scope="module")
def quiet_server(tmp_path_factory):
    db = str(tmp_path_factory.mktemp("gsd-off") / "off.db")
    _seed(db)
    settings = Settings(
        clusters=[ClusterConfig("crc-local", "https://api.crc.testing:6443", token_env="X")],
        db_path=db,
        login_capture_enabled=False,
        # The export module OFF, so the shared fixtures can keep the default (on) and the
        # absent-control state still has a server to assert against.
        ui_export_enabled=False,
    )
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(
        build_app(settings, run_poller=False), host="127.0.0.1", port=port,
        log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(f"{base}/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        raise RuntimeError("dashboard server did not start")
    yield base
    srv.should_exit = True
    thread.join(timeout=5)


class TestLoginsDisabled:
    """Capture off is a DIFFERENT state from capture on and quiet.

    Its own server, because `login_capture_enabled` is settings rather than data: conflating
    the two states sends a reader hunting for logins that were never going to be recorded.
    """

    def test_it_says_capture_is_off_and_names_both_halves(self, page, quiet_server):
        page.goto(quiet_server + "#page=logins&cluster=crc-local")
        page.wait_for_selector("h2:text-is('Login attempts')")
        body = page.locator("body").inner_text()
        assert "Not being captured" in body
        # BOTH halves, because either one alone records nothing: the module has to run, and the
        # operand has to be verbose enough to write a username at all. Since chart 0.14.0 the
        # module is on by default, so the card says that rather than prescribing the default.
        assert "chart default since 0.14.0 is on" in body
        assert "loginCapture.enabled=true" in body
        assert "config.loginCapture.enabled" not in body, "the old card named a key that does not exist"
        assert "authLogLevel.manage" in body
        assert "Debug" in body
        assert "audit log" in body
        # And it must not show the seeded rows as though they were live.
        assert "mallory" not in body


class TestClusterAccessPanel:
    """Who can actually LOG IN, set against who holds access.

    The one view here that does not start from RBAC, so it sees what none of the others can: a role
    granted to somebody who cannot authenticate. Every assertion is about a way this could mislead.
    """

    def _open(self, dash):
        dash.click('button.tab:text-is("Logins")')
        dash.wait_for_selector("h2:text-is('Cluster access')")

    def _card(self, dash, heading):
        return dash.locator("section.card", has=dash.locator(f"h3:text-is('{heading}')"))

    def test_the_panel_renders_and_names_the_gate_group(self, dash):
        errors = []
        dash.on("pageerror", lambda e: errors.append(str(e)))
        self._open(dash)
        body = dash.locator("body").inner_text()
        assert "app-ssb-autobahnusers" in body
        assert "Dashboard API error" not in body, body[:300]
        assert not errors, errors

    def test_the_dn_is_matched_case_insensitively(self, dash):
        """The seed stores `CN=...,OU=...,DC=...` while the Group carries `cn=...,ou=...,dc=...`.

        An exact comparison would report the gate group as not synced on a cluster where it is synced
        perfectly well — a false "prerequisite not met", which is the worst kind of wrong here because
        it looks like an instruction.
        """
        self._open(dash)
        body = dash.locator("body").inner_text()
        assert "no synced group matches it" not in body, (
            "the DN failed to match its own Group because of letter case"
        )
        assert self._card(dash, "Access that cannot be used").count() == 1

    def test_it_leads_with_the_finding_not_the_volume(self, dash):
        """`dave` holds access through a synced group and is not in the gate group."""
        self._open(dash)
        card = dash.locator("section.card", has=dash.locator("h2:text-is('Cluster access')"))
        assert card.locator(".hero .value").inner_text().strip() == "1"
        assert "cannot use" in card.locator(".hero .label").inner_text()

    def test_the_stranded_person_is_named_with_the_groups_that_grant_it(self, dash):
        self._open(dash)
        row = self._card(dash, "Access that cannot be used").locator("tbody tr").first.inner_text()
        assert "dave" in row, row
        assert "app-ocp-rbac-alpha-ns-admin" in row, (
            f"the grant is not shown, so the reader cannot act on the finding: {row}"
        )

    def test_a_gated_member_who_also_holds_access_is_not_a_finding(self, dash):
        """alice is in both. Reporting her would make the list noise."""
        self._open(dash)
        rows = self._card(dash, "Access that cannot be used").locator("tbody tr").all_inner_texts()
        assert not any("alice" in r for r in rows), rows

    def test_the_quieter_half_is_shown_separately(self, dash):
        """In the gate group, holds no access. Not automatically a problem — so its own section."""
        self._open(dash)
        rows = self._card(dash, "Allowed to log in, holds no access") \
            .locator("tbody tr").all_inner_texts()
        assert any("gatekeeper" in r for r in rows), rows
        assert not any("dave" in r for r in rows), "the two findings are being mixed"

    def test_provenance_is_stated(self, dash):
        """Configured or discovered. An operator asking "why is this the wrong group?" needs to know
        which of the two to change."""
        self._open(dash)
        card = dash.locator("section.card", has=dash.locator("h2:text-is('Cluster access')"))
        assert "discovered" in card.locator(".chip").first.inner_text()

    def test_the_stranded_person_drills_to_their_user_page(self, dash):
        """Through the same navigate() machinery as every other drill, so Back behaves identically."""
        self._open(dash)
        self._card(dash, "Access that cannot be used") \
            .locator('button.drill[data-user="dave"]').first.click()
        dash.wait_for_selector("#back-groups")
        assert dash.evaluate("() => view.page") == "groups"
        assert dash.evaluate("() => view.user") == "dave"
        assert dash.locator("#back-groups").inner_text().strip() == "← logins"


class TestTheRefusalVerdict:
    """The ambiguity the log cannot resolve, resolved.

    A refused directory login writes `no entries matching (<filter>)`, and because the filter carries
    the gate group, a real person outside it and a username that does not exist produce byte-identical
    lines. With gate membership known there is something to choose with.
    """

    def _rows(self, dash):
        dash.click('button.tab:text-is("Logins")')
        dash.wait_for_selector("h3:text-is('Every attempt')")
        card = dash.locator("section.card", has=dash.locator("h3:text-is('Every attempt')"))
        return {r.split("\n")[1] if "\n" in r else r: r
                for r in card.locator("tbody tr").all_inner_texts()}

    def test_a_known_person_outside_the_gate_group_is_named_as_one(self, dash):
        """bob is in no group NOW but has membership history, so the directory knows him."""
        self._open_and(dash)
        text = dash.locator("section.card", has=dash.locator(
            "h3:text-is('Every attempt')")).inner_text()
        assert "a real person, not in the gate group" in text, text[:400]

    def test_a_name_with_no_record_says_only_that(self, dash):
        """NOT "unknown account": this dashboard reads OpenShift, not the directory, so it cannot
        claim the account does not exist."""
        self._open_and(dash)
        text = dash.locator("section.card", has=dash.locator(
            "h3:text-is('Every attempt')")).inner_text()
        assert "no record of this name" in text, text[:400]
        assert "unknown account" not in text

    def test_an_outcome_that_already_has_a_cause_gets_no_second_one(self, dash):
        """A wrong password is not ambiguous, and must not acquire a competing explanation."""
        self._open_and(dash)
        card = dash.locator("section.card", has=dash.locator("h3:text-is('Every attempt')"))
        for row in card.locator("tbody tr").all_inner_texts():
            if "wrong password" in row:
                for verdict in ("a real person, not in the gate group", "no record of this name",
                                "our membership data disagrees"):
                    assert verdict not in row, f"bad_password acquired a refusal verdict: {row}"

    def _open_and(self, dash):
        dash.click('button.tab:text-is("Logins")')
        dash.wait_for_selector("h3:text-is('Every attempt')")


class TestTheGateChipAppliesOnlyWhereTheGateApplies:
    """The login gate governs the DIRECTORY provider. A local HTPasswd login never passes through it.

    Seen on the fixture as `developer  not in access group  break-glass`: a true statement about group
    membership that reads as a finding about an account the gate has no bearing on, sitting next to the
    chip that says so. Suppressed on those rows.
    """

    def test_a_break_glass_row_does_not_claim_a_gate_finding(self, dash):
        dash.click('button.tab:text-is("Logins")')
        dash.wait_for_selector("h3:text-is('Every attempt')")
        card = dash.locator("section.card", has=dash.locator("h3:text-is('Every attempt')"))
        for row in card.locator("tbody tr").all_inner_texts():
            if "break-glass" in row or "local provider" in row:
                assert "not in access group" not in row, (
                    f"the gate does not govern this provider, so the row must not imply it: {row}"
                )

    def test_a_directory_row_outside_the_gate_group_still_says_so(self, dash):
        """The suppression must be narrow: it applies to local providers, not to every row."""
        dash.click('button.tab:text-is("Logins")')
        dash.wait_for_selector("h3:text-is('Every attempt')")
        card = dash.locator("section.card", has=dash.locator("h3:text-is('Every attempt')"))
        rows = card.locator("tbody tr").all_inner_texts()
        assert any("not in access group" in r and "ldap-local" in r for r in rows), rows


class TestGroupSearch:
    """Free-text filter on the Groups tab. 64 groups on the reference cluster is too many to scan.

    The behaviour that matters is AND-of-terms, not substring-of-the-whole-query. Group names are long
    and structured — app-ocp-rbac-alpha-ns-admin — so the two halves a reader remembers are rarely
    adjacent: "alpha admin" has to find it, and as one substring it finds nothing.
    """

    def _open(self, dash):
        dash.locator("button[data-nav='groups']").click()
        # A DATA row, not #f-group-search: the tab handler paints the destination before it
        # fetches (2026-08-10), so the box appears immediately and no longer means "the
        # fetch landed". Only a fetched render produces tr[data-group]. Same reason in
        # every helper that clicks a tab and then reads its rows.
        dash.wait_for_selector("tr[data-group]")

    def _names(self, dash):
        return [r.split("\t")[0].strip() for r in dash.locator("tbody tr").all_inner_texts()]

    def test_a_single_term_is_a_substring_match(self, dash):
        self._open(dash)
        dash.fill("#f-group-search", "abcd")
        dash.wait_for_function("() => view.groupSearch === 'abcd'")
        names = self._names(dash)
        assert names == ["app-ocp-rbac-abcd-ns-superuser"], names

    def test_two_terms_are_ANDed_and_order_does_not_matter(self, dash):
        """The whole point. Neither ordering appears as a contiguous substring of the name."""
        self._open(dash)
        for query in ("alpha admin", "admin alpha"):
            dash.fill("#f-group-search", query)
            dash.wait_for_function(f"() => view.groupSearch === {query!r}")
            assert self._names(dash) == ["app-ocp-rbac-alpha-ns-admin"], (query, self._names(dash))
        # And prove the premise: as one substring it matches nothing.
        assert "alpha admin" not in "app-ocp-rbac-alpha-ns-admin"

    def test_it_is_case_insensitive(self, dash):
        self._open(dash)
        dash.fill("#f-group-search", "ALPHA Admin")
        dash.wait_for_function("() => view.groupSearch === 'ALPHA Admin'")
        assert self._names(dash) == ["app-ocp-rbac-alpha-ns-admin"]

    def test_a_term_matching_nothing_says_the_search_is_hiding_them(self, dash):
        """An empty table must not read as "there are no groups"."""
        self._open(dash)
        dash.fill("#f-group-search", "zzzznope")
        dash.wait_for_function("() => view.groupSearch === 'zzzznope'")
        body = dash.locator("section.card").first.inner_text()
        assert "No group name contains" in body, body[:200]
        assert "the search hiding them" in body or "search hiding them" in body, body[:300]

    def test_the_header_reports_the_denominator_while_filtering(self, dash):
        """A filtered view that cannot report what it hid is the same failure as a truncated page."""
        self._open(dash)
        whole = dash.locator("section.card h2").first.inner_text()
        assert "of" not in whole, whole
        dash.fill("#f-group-search", "abcd")
        dash.wait_for_function("() => view.groupSearch === 'abcd'")
        assert "1 of " in dash.locator("section.card h2").first.inner_text()

    def test_escape_clears_it(self, dash):
        self._open(dash)
        dash.fill("#f-group-search", "abcd")
        dash.wait_for_function("() => view.groupSearch === 'abcd'")
        dash.locator("#f-group-search").press("Escape")
        dash.wait_for_function("() => view.groupSearch === ''")
        assert len(self._names(dash)) == SYNCED_GROUPS

    def test_the_caret_and_focus_survive_a_repaint(self, dash):
        """THE ONE THAT MAKES IT USABLE. renderFilters replaces the whole bar's innerHTML and the page
        repaints every 30s, so without preservation the field loses focus after one character and the
        caret jumps to the end mid-word."""
        self._open(dash)
        dash.fill("#f-group-search", "alpha-admin")
        # Put the caret in the middle, then force the repaint the poll would cause.
        dash.locator("#f-group-search").evaluate("el => el.setSelectionRange(5, 5)")
        dash.evaluate("() => render()")
        state = dash.evaluate("""() => {
            const el = document.getElementById('f-group-search');
            return { focused: document.activeElement === el, start: el.selectionStart, value: el.value };
        }""")
        assert state["focused"], "focus was lost when the filter bar re-rendered"
        assert state["start"] == 5, f"the caret moved to {state['start']}"
        assert state["value"] == "alpha-admin"

    def test_searching_does_not_refetch(self, dash):
        """The endpoint applies no limit, so the whole list is already here. A request per keystroke
        would be slower and would also search only whatever came back."""
        dash.evaluate("() => { window.__calls = 0; const f = window.fetch;"
                      " window.fetch = (...a) => { window.__calls++; return f(...a); }; }")
        self._open(dash)
        before = dash.evaluate("() => window.__calls")
        dash.fill("#f-group-search", "alpha")
        dash.wait_for_function("() => view.groupSearch === 'alpha'")
        dash.wait_for_timeout(400)
        assert dash.evaluate("() => window.__calls") == before, "filtering issued a network request"

    def test_a_filtered_row_still_drills_in(self, dash):
        """Filtering must not break the affordance it exists to reach."""
        self._open(dash)
        dash.fill("#f-group-search", "alpha admin")
        dash.wait_for_function("() => view.groupSearch === 'alpha admin'")
        dash.locator("tr[data-group='app-ocp-rbac-alpha-ns-admin']").click()
        dash.wait_for_selector("#back-groups")
        assert dash.evaluate("() => view.group") == "app-ocp-rbac-alpha-ns-admin"

    def test_the_box_only_exists_on_the_groups_tab(self, dash):
        self._open(dash)
        assert dash.locator("#f-group-search").count() == 1
        dash.click('button.tab:text-is("Overview")')
        dash.wait_for_timeout(300)
        assert dash.locator("#f-group-search").count() == 0

    def test_the_visible_label_is_the_accessible_name(self, dash):
        """aria-label REPLACES the accessible name. A sentence there means a screen reader announces a
        paragraph where the visible label says "Find", and that mismatch breaks WCAG 2.5.3 Label in
        Name for anyone driving the page by voice: they say "click Find" and hit nothing.

        The help text is a DESCRIPTION, so it belongs behind aria-describedby.
        """
        self._open(dash)
        el = dash.locator("#f-group-search")
        assert el.get_attribute("aria-label") is None, "aria-label is overriding the visible label"
        assert el.get_attribute("aria-describedby") == "f-group-search-help"
        assert dash.locator("label[for='f-group-search']").inner_text().strip() == "Find"
        help_text = dash.locator("#f-group-search-help")
        assert "AND" in help_text.inner_text()
        # Present in the accessibility tree, and not on screen: a 1px clipped box, never display:none.
        assert help_text.evaluate("el => getComputedStyle(el).display") != "none"
        assert help_text.evaluate("el => el.getBoundingClientRect().width") <= 2


class TestGroupSearchIme:
    """CJK, and every other composed input, goes through an IME whose composition session is bound to
    the NODE it is composing into. renderFilters replaces that node, so a repaint mid-composition
    commits half-composed kana as literal text and the IME's next update opens a second session:
    typing かんり lands as かかんかんり. CDP's Input.imeSetComposition is a real composition as far as
    Blink is concerned — the same code path a macOS or Windows IME drives."""

    def _open(self, dash):
        dash.locator("button[data-nav='groups']").click()
        dash.wait_for_selector("tr[data-group]")
        dash.focus("#f-group-search")
        return dash.context.new_cdp_session(dash)

    def test_an_ime_composition_survives_its_own_input_events(self, dash):
        cdp = self._open(dash)
        cdp.send("Input.imeSetComposition", {"text": "か", "selectionStart": 1, "selectionEnd": 1})
        dash.wait_for_timeout(100)
        cdp.send("Input.imeSetComposition", {"text": "かん", "selectionStart": 2, "selectionEnd": 2})
        dash.wait_for_timeout(100)
        cdp.send("Input.insertText", {"text": "かんり"})
        dash.wait_for_timeout(100)
        got = dash.evaluate("() => document.getElementById('f-group-search').value")
        assert got == "かんり", f"the composition was aborted by a repaint: {got!r}"
        assert dash.evaluate("() => view.groupSearch") == "かんり"

    def test_the_poll_firing_mid_composition_does_not_abort_it(self, dash):
        """The 30s timer cannot be asked to wait for the reader's IME."""
        cdp = self._open(dash)
        cdp.send("Input.imeSetComposition", {"text": "か", "selectionStart": 1, "selectionEnd": 1})
        dash.wait_for_timeout(100)
        dash.evaluate("() => render()")  # exactly what the poll does
        dash.wait_for_timeout(100)
        cdp.send("Input.imeSetComposition", {"text": "かん", "selectionStart": 2, "selectionEnd": 2})
        dash.wait_for_timeout(100)
        cdp.send("Input.insertText", {"text": "かんり"})
        dash.wait_for_timeout(100)
        got = dash.evaluate("() => document.getElementById('f-group-search').value")
        assert got == "かんり", f"the poll's repaint aborted the composition: {got!r}"


class TestGroupSearchEmptyStateHonesty:
    def _open(self, dash):
        dash.locator("button[data-nav='groups']").click()
        dash.wait_for_selector("tr[data-group]")

    def test_a_zero_denominator_does_not_blame_the_search(self, dash):
        """With no groups matching the STATE filter the search hides nothing, so "it is the search
        hiding them" is false — the reader would clear a query that was never the cause and still
        see an empty table."""
        self._open(dash)
        # The shape the server returns for a state filter with no matches, plus an active search.
        dash.evaluate(
            "() => { view.groupFilter = 'empty'; data.groups = []; data.groupsMeta = {scope: 'all', viewer: null, state: 'empty'};"
            " view.groupSearch = 'admin'; render(); }")
        note = dash.locator(".empty-note").inner_text()
        assert "search hiding" not in note, note
        assert "No groups match this filter" in note, note

    def test_a_denominator_of_one_reads_as_one(self, dash):
        self._open(dash)
        dash.select_option("#f-state", "unattributed")
        dash.wait_for_function("() => data.groups.length === 1")
        dash.fill("#f-group-search", "zzz")
        dash.wait_for_function("() => view.groupSearch === 'zzz'")
        note = " ".join(dash.locator(".empty-note").inner_text().split())
        assert "1 group matches the state filter" in note, note
        assert "the search hiding it rather" in note, note


    def test_the_banner_does_not_promise_rows_that_do_not_exist(self, dash):
        """A zero denominator must not invite the reader to clear a search that is hiding nothing.

        The empty state below the table was fixed for this; the banner ABOVE it made the same false
        claim six lines earlier — "Clear the box ... to see all 0" — and clearing it shows the same
        empty table. Both sites state the same fact, so both have to be honest about it.
        """
        self._open(dash)
        dash.evaluate(
            "() => { view.groupFilter = 'empty'; data.groups = []; data.groupsMeta = {scope: 'all', viewer: null, state: 'empty'};"
            " view.groupSearch = 'admin'; render(); }")
        card = " ".join(dash.locator("section.card").first.inner_text().split())
        assert "to see all 0" not in card, (
            f"the banner offers to show all 0 groups; clearing the box shows the same empty table: {card}"
        )
        assert "Filtered by admin" in card, f"the banner should still say a filter is applied: {card}"

    def test_the_banner_still_offers_the_count_when_there_is_one(self, dash):
        """The guard above must not silence the offer in the case it was written for."""
        self._open(dash)
        dash.select_option("#f-state", "unattributed")
        dash.wait_for_function("() => data.groups.length === 1")
        dash.fill("#f-group-search", "zzz")
        dash.wait_for_function("() => view.groupSearch === 'zzz'")
        card = " ".join(dash.locator("section.card").first.inner_text().split())
        assert "to see all 1" in card, card


class TestGroupSearchScroll:
    def test_the_poll_does_not_yank_the_viewport_while_the_box_is_focused(self, dash):
        """focus() scrolls its target into view, and the restored box sits at the top of the page —
        so with focus parked in the search box, every poll would jump a reader who had scrolled
        into the table back to the top."""
        dash.locator("button[data-nav='groups']").click()
        dash.wait_for_selector("tr[data-group]")
        dash.set_viewport_size({"width": 900, "height": 400})
        dash.focus("#f-group-search")
        dash.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        before = dash.evaluate("() => window.scrollY")
        assert before > 0, "page too short to scroll — shrink the viewport further"
        dash.evaluate("() => render()")  # the 30s poll
        after = dash.evaluate("() => window.scrollY")
        assert after == before, f"the repaint scrolled the page from {before} to {after}"
        assert dash.evaluate(
            "() => document.activeElement === document.getElementById('f-group-search')")


class TestTabFocusSurvivesTheRepaint:
    def test_a_keyboard_user_resting_on_a_tab_keeps_it_across_the_poll(self, dash):
        """The restore machinery finds elements by id, and the nav tabs had none — so the reader who
        tabbed to "Groups" and paused was silently dropped to <body> by the next poll."""
        dash.focus("button[data-nav='groups']")
        dash.evaluate("() => render()")  # the 30s poll
        got = dash.evaluate("() => document.activeElement.dataset && document.activeElement.dataset.nav")
        assert got == "groups", f"focus fell to {got!r} when the filter bar re-rendered"


class TestTheDeadSessionPanel:
    """What the reader sees when the 4-hour cap arrives mid-read.

    The proxy answers an expired cookie with a 302 to the login page, and fetch FOLLOWS
    redirects — so the page receives a 200 whose body is HTML and res.json() throws a syntax
    error about an unexpected "<". Untreated, that reads as a broken dashboard rather than a
    finished session, which is the worst possible reading for somebody mid-audit.
    """

    def test_an_auth_redirect_reads_as_a_finished_session_not_a_parse_error(self, dash):
        dash.evaluate("""() => { window.fetch = async () => new Response('<html>login</html>',
            {status: 200, headers: {'Content-Type': 'text/html'}}); }""")
        dash.evaluate("() => refresh()")
        dash.wait_for_function("() => document.getElementById('main').innerText.includes('session')")
        body = dash.locator("#main").inner_text()
        assert "session has ended" in body, body
        assert "JSON" not in body and "Unexpected" not in body, (
            f"a parse error reached the reader instead of an explanation: {body}")
        # It must also say what was NOT affected: a reader mid-audit should not be left
        # wondering whether the rows they just read were wrong.
        assert "before this point" in body, body

    def test_the_sign_out_control_is_withdrawn_once_the_session_is_gone(self, dash):
        dash.evaluate("""() => { window.fetch = async () => new Response('<html>login</html>',
            {status: 200, headers: {'Content-Type': 'text/html'}}); }""")
        dash.evaluate("() => refresh()")
        dash.wait_for_function("() => document.getElementById('main').innerText.includes('session')")
        assert dash.locator("#logout").is_hidden(), (
            "offering to sign out of a session that has already ended is an action that "
            "cannot work")
        assert dash.locator('#main a[href="/"]').count() > 0, "no way back in was offered"

@pytest.fixture(scope="module")
def proxied_server(tmp_path_factory):
    """A dashboard that believes the oauth-proxy is in front of it.

    The shared `server` fixture runs with the proxy OFF, which is the right default for the
    rest of this suite and the wrong one for the sign-out control: whoami refuses identity in
    that mode, so the control is correctly hidden and its visible state cannot be reached. The
    browser context supplies the identity headers the sidecar would add.
    """
    db = str(tmp_path_factory.mktemp("gsd-proxied") / "ui.db")
    _seed(db)
    settings = Settings(
        clusters=[ClusterConfig("crc-local", "https://api.crc.testing:6443", token_env="X")],
        db_path=db,
        oauth_proxy_enabled=True,
    )
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(
        build_app(settings, run_poller=False), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(f"{base}/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        raise RuntimeError("dashboard server did not start")
    yield base
    srv.should_exit = True
    thread.join(timeout=5)


# ── Per-user visibility: how a narrowed view is LABELLED ─────────────────────────────────
# The server decides the tier; the page renders `scope`/`viewer` off the wire and a
# designed 403 as a named refusal. These tests hold the page to exactly that — including
# the negative: no declaration on the wire, no label on the page.


class _TierByName:
    """The seam the visibility feature publishes for tests: build_app leaves its resolver
    at app.state.tier_resolver and every handler reads it per request, so swapping it here
    controls the tier without a cluster. `root` is the administrator persona; everyone
    else is self."""

    def resolve(self, viewer):
        return "all" if viewer == "root" else "self"


@pytest.fixture(scope="module")
def scoped_server(tmp_path_factory):
    """The seeded app behind a simulated oauth proxy, restrictions ON (the D1 default)."""
    db = str(tmp_path_factory.mktemp("gsd-vis") / "ui.db")
    _seed(db)
    settings = Settings(
        clusters=[
            ClusterConfig("crc-local", "https://api.crc.testing:6443", token_env="X"),
            ClusterConfig("prod-east", "https://api.prod-east.example.com:6443", token_env="Y"),
        ],
        db_path=db,
        login_capture_enabled=True,
        # Identity is believable here, unlike in the plain `server` fixture: the tier is
        # keyed off X-Forwarded-User, which is exactly what the proxy would set.
        oauth_proxy_enabled=True,
    )
    port = _free_port()
    app = build_app(settings, run_poller=False)
    app.state.tier_resolver = _TierByName()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    srv = uvicorn.Server(config)
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(f"{base}/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        raise RuntimeError("dashboard server did not start")
        raise RuntimeError("scoped dashboard server did not start")
    yield base
    srv.should_exit = True
    thread.join(timeout=5)


class TestSignOutControl:
    """The header's Sign out link, up to the proxy hop the proxy itself owns."""

    def test_it_is_offered_and_aims_at_the_proxys_sign_out(self, browser, proxied_server):
        """whoami said authenticated, so the control appears — pointing at the proxy's own
        sign_out, composed from the configured prefix rather than hardcoded."""
        ctx = browser.new_context(extra_http_headers={
            "X-Forwarded-User": "alice", "X-Forwarded-Email": "a@x.com"})
        page = ctx.new_page()
        try:
            page.goto(proxied_server)
            # Not `.hero .value`: since #158 the landing page is Home, which carries no cluster
            # hero for anyone. This wait only wants to know that the page painted.
            page.wait_for_selector("#main .card", timeout=10_000)
            link = page.locator("#logout")
            assert link.is_visible()
            assert link.get_attribute("href") == "/oauth/sign_out"
            assert "alice" in (link.get_attribute("title") or ""), (
                "the control should name whose session it ends")
        finally:
            ctx.close()

    def test_the_quoted_cap_comes_from_the_server_not_the_page(self, browser, proxied_server):
        """The page must not hardcode 4 hours: if it did, an operator lowering
        oauthProxy.cookie.expire would leave it telling readers a number the proxy no longer
        enforces."""
        ctx = browser.new_context(extra_http_headers={"X-Forwarded-User": "alice"})
        page = ctx.new_page()
        try:
            page.goto(proxied_server)
            # Not `.hero .value`: since #158 the landing page is Home, which carries no cluster
            # hero for anyone. This wait only wants to know that the page painted.
            page.wait_for_selector("#main .card", timeout=10_000)
            page.wait_for_function("() => sessionCapNote !== ''", timeout=10_000)
            assert page.evaluate("() => sessionCapNote") == "4-hour"
            # Proof it is derived: feed a different duration and the note follows.
            note = page.evaluate("""() => {
                const s = 1800 / 3600;
                return s >= 1 ? `${+s.toFixed(1)}-hour` : `${Math.round(s * 60)}-minute`;
            }""")
            assert note == "30-minute", note
        finally:
            ctx.close()

    def test_no_control_without_a_session(self, dash):
        """The shared fixture runs the proxy OFF, where whoami refuses identity — so offering
        to end a session that does not exist is exactly the lie the gate prevents."""
        assert dash.locator("#logout").is_hidden()
def _open_as(page, base, user):
    """Load the dashboard as `user`, with an uncaught JS error an immediate failure —
    the same discipline as the `dash` fixture, for the same reason."""
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.set_extra_http_headers({"X-Forwarded-User": user})
    page.goto(base)
    try:
        # `#main .card`, not `.hero .value`: since #158 the landing page is Home, which carries no
        # cluster hero for any tier. Home, a refusal and the Overview all render a section.card,
        # which is what this wait actually wants to know — that the page painted.
        page.wait_for_selector("#main .card", timeout=10_000)
    except Exception:
        if errors:
            pytest.fail("the page raised and never rendered:\n  " + "\n  ".join(errors))
        raise
    assert not errors, "uncaught JS error on load:\n  " + "\n  ".join(errors)
    return page



def _home(page, base, user="alice"):
    """Home as `user`, waited on its own paint — the pill and the tab strip arrive before the payload."""
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.set_extra_http_headers({"X-Forwarded-User": user})
    page.goto(base)
    page.wait_for_selector(".home .answer, .home .scope-refusal", timeout=10_000)
    assert not errors, "uncaught JS error on Home:\n  " + "\n  ".join(errors)
    return page


class TestHome:
    """#158: Home is the page every reader lands on — their own access, on every tier, from
    `docs/design/landing-access-mock.html`. Self-scoped by definition, so the shape is the same for a
    narrowed reader and an administrator; the arithmetic is the server's (gsd/home.py) and the page only
    composes sentences from it."""

    def test_home_is_the_default_route_and_the_first_tab(self, page, scoped_server):
        p = _home(page, scoped_server)
        assert p.evaluate("() => view.page") == "home"
        assert p.locator("button.tab").first.inner_text().strip() == "Home"
        assert p.locator("#tab-home[aria-current='page']").count() == 1
        assert p.evaluate("() => document.body.dataset.page") == "home", "the section accent follows the page"

    def test_the_answer_leads_with_one_sentence_and_its_tags(self, page, scoped_server):
        p = _home(page, scoped_server)
        h1 = p.locator(".home .answer h1").inner_text()
        assert h1.endswith("on crc-local"), h1
        assert "Signed in as" in p.locator(".home .answer .who").inner_text()
        tags = [t.strip() for t in p.locator(".home .tag").all_inner_texts()]
        assert any("group" in t and "grant" in t for t in tags), tags

    def test_every_row_is_a_button_the_keyboard_reaches(self, page, scoped_server):
        """The mock's rows are whole-row controls; a div with a click handler is unreachable by keyboard
        (the defect #167's and #174's reviews both found on other pages)."""
        p = _home(page, scoped_server)
        shapes = p.evaluate("""() => [...document.querySelectorAll('.home .hrow')].map(
            r => [r.tagName, r.classList.contains('static'), r.getAttribute('type')])""")
        assert shapes, "no rows rendered"
        for tag, static, typ in shapes:
            assert tag == ("DIV" if static else "BUTTON"), shapes
            assert static or typ == "button", "a bare <button> inside a form would submit it"

    def test_a_group_row_drills_to_that_group_and_back_returns_to_home(self, page, scoped_server):
        p = _home(page, scoped_server)
        row = p.locator(".home [data-group]").first
        name = row.locator(".name").inner_text().strip()
        row.click()
        p.wait_for_selector(f"h2:text-is('{name}')")
        assert p.evaluate("() => view.page") == "groups"
        p.go_back()
        p.wait_for_selector(".home .answer")
        assert p.evaluate("() => view.page") == "home"

    def test_the_folds_are_view_state_never_a_position(self, page, scoped_server):
        """Expanding "show all" is not a place to come back to: it must not push a history entry."""
        p = _home(page, scoped_server)
        fold = p.locator(".home [data-home-show]")
        if not fold.count():
            pytest.skip("this seed has no folded group list")
        before = p.evaluate("() => history.length")
        fold.first.click()
        p.wait_for_function("(n) => document.querySelectorAll('.home .hrow').length > n",
                            arg=p.evaluate("() => document.querySelectorAll('.home .hrow').length") - 1)
        assert p.evaluate("() => history.length") == before
        assert p.evaluate("() => location.hash").startswith("#page=home")

    def test_an_administrator_sees_their_own_access_here_not_the_clusters(self, page, scoped_server):
        """The DoD's central claim: no admin aggregate may leak here. root is in no synced group in the
        seed, so their Home says so rather than showing the cluster's groups."""
        p = _home(page, scoped_server, "root")
        assert p.locator("#scope-pill").inner_text().startswith("Full view")
        text = p.locator(".home").inner_text()
        assert "You are in no synced group here" in text.replace("\n", " "), text[:400]
        assert "alice" not in text and "gatekeeper" not in text, "another person's name on a self-scoped page"

    def test_the_cluster_selector_rescopes_and_a_cluster_that_vouches_for_nobody_says_so(self, page, scoped_server):
        """The cluster is a position; switching re-scopes the answer without leaving Home. `prod-east` is
        not the host cluster and its identity policy is the default `none` — it does not treat the host's
        username as its own — so Home there is a refusal in its own words, never an API error and never a
        page that quietly answers for a name nobody vouched for (docs/ACCESS_CONTROL.md §11)."""
        p = _home(page, scoped_server)
        assert "crc-local" in p.locator(".home .answer h1").inner_text()
        p.select_option("#f-cluster", "prod-east")
        p.wait_for_function("() => view.cluster === 'prod-east'")
        p.wait_for_selector(".home .scope-refusal")
        assert p.evaluate("() => view.page") == "home", "the cluster is a position, the page is not"
        refusal = p.locator(".home .scope-refusal").inner_text()
        assert "does not treat your identity as one of its own" in refusal, refusal
        assert "Dashboard API error" not in p.locator("#main").inner_text()
        p.select_option("#f-cluster", "crc-local")
        p.wait_for_selector(".home .answer h1")
        assert "crc-local" in p.locator(".home .answer h1").inner_text(), "and back"

    def test_no_identity_says_so_in_its_own_words_not_as_an_api_error(self, page, scoped_server):
        """The proxy passing no username is a refusal the page explains, never "Dashboard API error"."""
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{scoped_server}/#page=home&cluster=prod-east")
        page.wait_for_selector(".home .card")
        text = page.locator(".home").inner_text()
        assert "Dashboard API error" not in text, text[:300]
        assert not errors

    def test_the_cluster_wide_foot_never_says_zero_groups_grant(self, page, scoped_server):
        """A cluster-wide role held only by a DIRECT grant has no groups behind it; the card's foot read
        "0 groups grant edit cluster-wide … removing them would not change what you can do" (Grok, review
        of #158). Painted from the payload that produced it."""
        p = _home(page, scoped_server)
        p.evaluate("""() => {
          data.home.answer.cluster_wide = [
            {role_name: "admin", role_kind: "ClusterRole", via_groups: [], direct: true, bindings: 1, covered_by: null},
            {role_name: "edit", role_kind: "ClusterRole", via_groups: [], direct: true, bindings: 1, covered_by: "admin"}];
          data.home.answer.top_role = "admin";
          render();
        }""")
        foot = p.locator(".home .c-wide .foot").inner_text()
        assert "0 groups grant" not in foot, foot
        assert "A direct cluster-wide" in foot and "includes it by default" in foot, foot

    def test_the_more_line_reads_as_one_change_at_one(self, page, scoped_server):
        p = _home(page, scoped_server)
        p.evaluate("""() => { data.home.changes.more = 1; data.home.changes.more_items = 1;
          if (!data.home.changes.items.length) data.home.changes.items = [{kind: "single", cluster: "crc-local",
            change: "added", group_name: "g", observed_at: new Date().toISOString()}];
          render(); }""")
        assert "1 more change in the window" in p.locator(".home .c-changes").inner_text()

    def test_the_window_named_on_the_card_is_the_one_the_rows_were_selected_by(self, page, scoped_server):
        """The page carried its own copy of the 30-day window. Two constants for one number drift the
        moment either moves, and the card would name a window the rows were not selected by (Grok,
        review of #158). The window arrives with the payload."""
        p = _home(page, scoped_server)
        assert "last 30 days" in p.locator(".home .c-changes h2").inner_text()
        p.evaluate("() => { data.home.changes.window_days = 7; render(); }")
        assert "last 7 days" in p.locator(".home .c-changes h2").inner_text()

    def test_the_poll_age_pill_is_not_the_shells_refetch_dim(self, page, scoped_server):
        """The pill was called `.stale`, which is the shell's refetch state — a global `opacity: 0.55` on
        whatever carries it — so it rendered at 55 % and measured 2.27:1 (Codex, review of #158). One class
        cannot mean both "this page is being refetched" and "this cluster's data is old"."""
        p = _home(page, scoped_server)
        p.evaluate("""() => {
          data.home.elsewhere = [{cluster: "prod-east", memberships: 3, status: "auth_failed", last_poll: "2026-01-01T00:00:00Z"}];
          data.home.memberships_total = 5; render();
        }""")
        pill = p.locator(".home .poll-age")
        assert pill.count() == 1, p.locator(".home .xcluster").inner_text()
        assert p.locator(".home .stale").count() == 0, "the shell's refetch class is on the pill"
        assert p.evaluate("() => getComputedStyle(document.querySelector('.home .poll-age')).opacity") == "1"

    def test_a_retention_window_of_forever_does_not_claim_rows_were_pruned(self, page, scoped_server):
        """`window_days: 0` is "kept forever", so the oldest row held is where the dashboard began watching,
        not a cut — saying "pruned" of it invents a deletion (Codex, review of #158)."""
        p = _home(page, scoped_server)
        p.evaluate("""() => { data.home.retention = {window_days: 0, retained_since: "2026-08-02T00:00:00Z"};
          render(); }""")
        foot = p.locator(".home .c-changes .foot").inner_text()
        assert "pruned" not in foot.replace("nothing is pruned", ""), foot
        assert "where this dashboard began watching" in foot, foot
        p.evaluate("""() => { data.home.retention = {window_days: 90, retained_since: "2026-08-02T00:00:00Z"};
          render(); }""")
        assert "have been pruned by retention" in p.locator(".home .c-changes .foot").inner_text()

    def test_two_paths_of_different_kinds_are_not_called_the_same_grant(self, page, scoped_server):
        """A Role and a ClusterRole of one name are two objects — the collision the ranking already fixed
        (Codex, review of #158)."""
        p = _home(page, scoped_server)
        p.evaluate("""() => {
          const grant = (kind, group) => ({role_name: "admin", role_kind: kind, via_group: group,
                                           binding_name: "b-" + group, covered: false});
          data.home.answer.namespaces = [
            {name: "same", platform: false, covered: false, grants: [grant("ClusterRole", "g1"), grant("ClusterRole", "g2")]},
            {name: "mixed", platform: false, covered: false, grants: [grant("ClusterRole", "g1"), grant("Role", "g2")]}];
          render();
        }""")
        rows = p.evaluate("""() => Object.fromEntries([...document.querySelectorAll('.home .c-ns .hrow')].map(
            r => [r.querySelector('.name').textContent.trim(), r.querySelector('.meta').textContent]))""")
        assert "paths to the same grant" in rows["same"], rows
        assert "paths to the same grant" not in rows["mixed"], rows

    def test_the_labels_keep_the_units_of_the_numbers_beside_them(self, page, scoped_server):
        """`answer.namespaces` are NAMESPACES; the sub-line called their count "namespace grants", so the
        deployed page read "covers 12 of your 13 namespace grants" over 13 namespaces. And the tag read
        "1 / 1 groups grant" at one (Codex, review of #158)."""
        p = _home(page, scoped_server)
        p.evaluate("""() => {
          const a = data.home.answer;
          a.top_role = "admin"; a.namespaces_covered = 2;
          a.namespaces = ["one", "two", "three"].map(n => ({name: n, platform: false, covered: n !== "three",
            grants: [{role_name: "edit", role_kind: "ClusterRole", via_group: "g", binding_name: "b", covered: n !== "three"}]}));
          a.groups_total = 1; a.groups_granting = 1;
          render();
        }""")
        sub = p.locator(".home .answer .sub").inner_text()
        assert "namespaces you reach" in sub and "namespace grants" not in sub, sub
        tags = " | ".join(p.locator(".home .tag").all_inner_texts())
        assert "1 / 1 group grants" in tags, tags

    def test_a_capped_history_says_its_counts_are_a_lower_bound(self, page, scoped_server):
        """Each cluster's history is read up to a cap, so on a busy one the card's count is a lower bound;
        showing it as complete would overclaim (Codex, review of #158)."""
        p = _home(page, scoped_server)
        p.evaluate("() => { data.home.changes.capped_clusters = ['crc-local', 'prod-east']; render(); }")
        foot = p.locator(".home .c-changes .foot").inner_text()
        assert "at least this many" in foot and "crc-local" in foot and "prod-east" in foot, foot
        p.evaluate("() => { data.home.changes.capped_clusters = []; render(); }")
        assert "at least this many" not in p.locator(".home .c-changes .foot").inner_text()

    def test_the_page_holds_at_375(self, page, scoped_server):
        page.set_viewport_size({"width": 375, "height": 740})
        p = _home(page, scoped_server)
        assert p.evaluate("() => document.documentElement.scrollWidth <= innerWidth"), "the page scrolls sideways"
        assert p.evaluate("() => [...document.querySelectorAll('.home .hrow')].every(r => r.getBoundingClientRect().right <= innerWidth + 1)")

    def test_a_long_role_name_does_not_squeeze_the_name_column_to_one_character(self, page, scoped_server):
        """Measured on the rendered page at 375: `group-sync-dashboard-report-auditor` in a nowrap pill took
        the row's whole width and stacked the group's name one character per line. The name keeps a floor it
        cannot be squeezed below, and a pill that will not fit beside it wraps under instead."""
        page.set_viewport_size({"width": 375, "height": 740})
        p = _home(page, scoped_server)
        p.evaluate("""() => {
          data.home.answer.cluster_wide = [{role_name: "group-sync-dashboard-report-auditor-with-a-very-long-name",
            role_kind: "ClusterRole", via_groups: ["app-ocp-rbac-groupsync-ns-auditor"], direct: false, bindings: 1, covered_by: null}];
          render();
        }""")
        cell = p.evaluate("""() => { const n = document.querySelector('.home .c-wide .hrow .name');
            const r = n.getBoundingClientRect(); return {w: Math.round(r.width), h: Math.round(r.height)}; }""")
        assert cell["w"] >= 150, f"the name column collapsed to {cell['w']}px"
        assert cell["h"] <= 80, f"the name stacked to {cell['h']}px tall"



class TestHomeSkipsTheUnchangedPoll:
    """The shell fingerprints every payload so an automatic poll that changed nothing does not replace
    `#main` — the reader's scroll, selection and focus survive. `/home` echoed the request's clock
    (`changes.since`, second precision), so on Home the fingerprint never matched and every 60 s poll
    repainted the page (OB3, integration review, C3: three polls, three repaints, one moving field)."""

    def test_two_automatic_polls_of_an_unchanged_store_leave_the_dom_alone(self, page, scoped_server):
        p = _home(page, scoped_server)
        p.wait_for_timeout(1500)   # the boot render has landed; nothing else is in flight
        p.evaluate("() => { document.querySelector('.home .answer h1').dataset.sentinel = 'kept'; }")
        for _ in range(2):
            p.evaluate("() => refresh({auto: true})")
            p.wait_for_timeout(1500)
        assert p.evaluate("() => document.querySelector('.home .answer h1').dataset.sentinel") == "kept", \
            "an automatic poll of an unchanged store repainted Home"


class TestVisibilityLabels:
    def test_the_pill_names_the_narrowed_view(self, page, scoped_server):
        """Q6/DoD 5: the reader can tell 'this is your view' from 'this is everything',
        on every tab, starting with the landing page — which since #158 is Home, not the Overview.

        The landing page no longer refuses a narrowed reader: Home is self-scoped by definition, so
        alice lands on her own access and the pill still names the tier she is on. The Overview's
        refusal is unchanged and is asserted below, one click away (#169's ruling)."""
        p = _open_as(page, scoped_server, "alice")
        p.wait_for_selector("#scope-pill:not([hidden])")
        text = p.locator("#scope-pill").inner_text()
        assert text.startswith("Your view"), text
        assert "alice" in text, "the pill must name the viewer it is scoped to"
        p.wait_for_selector(".home .answer")   # the pill rides whoami; Home waits on its own payload
        assert p.locator(".home .answer").count() == 1, "a narrowed reader lands on Home, not a refusal"
        assert p.locator(".scope-refusal").count() == 0
        p.locator("button[data-nav='overview']").click()
        p.wait_for_selector(".scope-refusal")
        assert p.locator(".hero").count() == 0, "the Overview stays the administrator tier's"

    def test_the_administrator_is_told_they_see_everything(self, page, scoped_server):
        """The admin marker. 'Nothing looks different' and 'you are seeing everything'
        are different statements, and only the second is checkable from the screen.

        Since #158 the administrator lands on Home too — their OWN access, never everyone's — and
        the Overview's cluster hero is one click away."""
        p = _open_as(page, scoped_server, "root")
        p.wait_for_selector("#scope-pill:not([hidden])")
        assert p.locator("#scope-pill").inner_text().startswith("Full view")
        p.wait_for_selector(".home .answer")
        assert p.locator(".home .answer").count() == 1
        assert p.locator(".scope-refusal").count() == 0
        p.locator("button[data-nav='overview']").click()
        p.wait_for_selector(".hero .value")
        assert p.locator(".hero").count() == 1

    def test_an_unknown_tier_does_not_paint_the_wide_overview(self, page, scoped_server):
        """A failed whoami is not evidence that the reader may see cluster-wide health."""
        page.route("**/api/whoami", lambda route: route.fulfill(
            status=503, content_type="application/json", body="{}"))
        page.set_extra_http_headers({"X-Forwarded-User": "alice"})
        page.goto(f"{scoped_server}/#page=overview")
        page.wait_for_selector("#main .card", timeout=10_000)
        assert page.locator("#main .hero").count() == 0

    def test_an_unknown_tier_does_not_paint_a_refusal(self, page, scoped_server):
        """Cold-load uncertainty is not evidence of narrowing either; wait for the authority."""
        page.route("**/api/whoami", lambda route: route.fulfill(
            status=503, content_type="application/json", body="{}"))
        page.set_extra_http_headers({"X-Forwarded-User": "alice"})
        page.goto(f"{scoped_server}/#page=overview")
        page.wait_for_selector("#main .card", timeout=10_000)
        assert page.locator("#main .scope-refusal").count() == 0
        assert page.locator("#main").inner_text().strip() == "Loading…"

    def test_an_unauthenticated_whoami_body_paints_the_wide_overview(self, page, scoped_server):
        """Without a verified identity no tier applies, so silence must not invent narrowing."""
        page.goto(f"{scoped_server}/#page=overview")
        page.wait_for_selector("#main .card", timeout=10_000)
        assert page.locator("#main .hero").count() == 1
        assert page.locator("#main .scope-refusal").count() == 0

    def test_groups_tab_banner_and_scoped_count(self, page, scoped_server):
        p = _open_as(page, scoped_server, "alice")
        p.locator("button[data-nav='groups']").click()
        p.wait_for_selector(".scope-banner")
        banner = p.locator(".scope-banner").inner_text()
        assert "alice" in banner and "belongs to" in banner
        # alice is in the RBAC group and the gate group — 2 of the 4 seeded groups.
        assert p.locator("tbody tr").count() == 2

    def test_admin_groups_tab_is_complete_and_carries_no_self_banner(self, page, scoped_server):
        p = _open_as(page, scoped_server, "root")
        p.locator("button[data-nav='groups']").click()
        p.wait_for_selector("tr[data-group]")
        assert p.locator("tbody tr").count() == SYNCED_GROUPS
        assert p.locator(".scope-banner").count() == 0

    def test_group_source_dots_still_colour_at_the_narrowed_tier(self, page, scoped_server):
        """crSlot reads provider_keys off data.groupsyncs — the ONE field of the self-tier
        /groupsyncs projection the Groups tab consumes. This is the silent-regression case
        the projection could ship: withhold provider_keys and no error fires anywhere —
        crSlot returns null, every source dot quietly vanishes, and a narrowed reader
        mis-reads the missing decoration as "unmapped provider" rather than "withheld".
        So the dots themselves are pinned, at the tier that actually receives the
        projected payload."""
        p = _open_as(page, scoped_server, "alice")
        p.locator("button[data-nav='groups']").click()
        p.wait_for_selector(".scope-banner")
        assert p.locator("tbody .cr-dot").count() > 0, (
            "no source dot painted on the narrowed Groups tab — provider_keys went "
            "missing from the self-tier /groupsyncs payload"
        )

    def test_scoped_empty_is_not_mistaken_for_an_empty_cluster(self, page, scoped_server):
        """Q6's founding example: one row where an administrator sees two hundred must
        not read as a nearly-empty cluster — and a scoped ZERO rows must not read as an
        empty one. The wording also surfaces the viewer's name, which is the on-screen
        diagnostic for an IdP-vs-synced-name mismatch."""
        p = _open_as(page, scoped_server, "nomember")
        p.locator("button[data-nav='groups']").click()
        p.wait_for_selector(".scope-banner")
        body = p.locator("#main").inner_text()
        assert "not a member of any synced group" in body
        assert "nomember" in body
        assert "No groups match this filter" not in body

    def test_nsaudit_self_view_names_the_viewer_and_drops_cluster_kpis(self, page, scoped_server):
        """Q5: 'People exposed' recomputed over one person is a lying label, so the
        narrowed tab renders the viewer's own grants and none of the cluster KPIs."""
        p = _open_as(page, scoped_server, "alice")
        p.locator("button[data-nav='nsaudit']").click()
        p.wait_for_selector(".scope-banner")
        body = p.locator("#main").inner_text()
        assert "No role is granted directly to" in body and "alice" in body
        assert "People exposed" not in body
        assert "Namespaces at risk" not in body

    def test_logins_tab_banner_carries_the_as_typed_caveat(self, page, scoped_server):
        """Byte-exact matching means a caps-lock attempt is invisible to its own author;
        the banner says so instead of letting the absence read as 'never happened'."""
        p = _open_as(page, scoped_server, "alice")
        p.locator("button[data-nav='logins']").click()
        p.wait_for_selector(".scope-banner")
        banner = p.locator(".scope-banner").first.inner_text()
        assert "alice" in banner and "as typed" in banner
        main = p.locator("#main").inner_text()
        assert "Accounts in no synced group" not in main, (
            "the ungoverned-accounts finding is whole-cluster data and must not render "
            "at the narrowed tier"
        )
        assert "bob" not in main, "another person's attempts leaked into the scoped view"

    def test_admin_logins_page_is_unchanged(self, page, scoped_server):
        p = _open_as(page, scoped_server, "root")
        p.locator("button[data-nav='logins']").click()
        # A logins-page element, not a bare "table": the overview's tables are still
        # painted while the logins fetch is in flight, so waiting on "table" races.
        p.wait_for_selector("h3:has-text('Every attempt')")
        body = p.locator("#main").inner_text()
        assert "Accounts in no synced group" in body
        assert p.locator(".scope-banner").count() == 0

    def test_group_drilldown_refusal_is_a_detour_not_a_dead_end(self, page, scoped_server):
        """The constant 403 must render as a named refusal WITH a working back affordance
        — and must not claim to know whether the group exists, because the server
        deliberately answers nonexistent and forbidden identically."""
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.set_extra_http_headers({"X-Forwarded-User": "alice"})
        page.goto(scoped_server + "#page=groups&group=app-ocp-rbac-abcd-ns-superuser")
        page.wait_for_selector(".scope-refusal")
        assert not errors
        assert "indistinguishable" in page.locator(".scope-refusal").inner_text()
        assert page.locator(".back").count() == 1

    def test_the_admin_only_tabs_say_so_exactly_once_and_offer_no_route_in(self, page, scoped_server):
        """The three administrator-tier tabs, as the operator specified them: each says "For
        administrators only" and each says it ONCE.

        Cardinality is pinned because it broke: the phrase was added to refusalCard's body AND
        left on all three call sites, so every refusal printed it twice. refusalCard owns the
        sentence now — a new refusal gets it for free and cannot double it.

        The second half is the operator's other instruction: the card must not name the grant,
        the role, the check or the chart. This text is read by the person being refused, who
        cannot act on any of it, and naming the permission that would lift the restriction
        turns a refusal into a shopping list.
        """
        # Access granted left this list on 2026-09-03: a narrowed reader now sees their own
        # grants there (TestAccessGrantedSelfTier), and only the two cluster-wide tabs refuse.
        for tab in ("overview", "policy"):
            p = _open_as(page, scoped_server + f"#page={tab}&cluster=crc-local", "alice")
            p.wait_for_selector(".scope-refusal")
            text = p.locator(".scope-refusal").inner_text()
            assert text.count("For administrators only") == 1, (
                f"{tab}: expected the phrase exactly once, got {text.count('For administrators only')}"
            )
            for leak in ("cluster-reader", "chart README", "adminSar", "visibility.enabled",
                         "SubjectAccessReview", "ClusterRole"):
                assert leak not in text, (
                    f"{tab}: the refusal names {leak!r} — a reader who cannot reach it, and "
                    f"should not be handed the route in"
                )

    def test_no_declaration_on_the_wire_means_no_labels(self, page, server):
        """The search-box scar as a regression test: the page must not claim a narrowing
        the response never declared. The plain `server` fixture runs restrictions-off
        with the proxy off — its responses carry scope 'all' or nothing — so the pill
        must exist (it is part of the header) and stay hidden, and no self banner may
        render anywhere."""
        page.goto(f"{server}/#page=overview")
        page.wait_for_selector(".hero .value", timeout=10_000)
        assert page.locator("#scope-pill").count() == 1, "the pill mount is missing from the header"
        assert page.locator("#scope-pill").is_hidden()
        page.locator("button[data-nav='groups']").click()
        page.wait_for_selector("tr[data-group]")
        assert page.locator(".scope-banner").count() == 0
        assert page.locator(".scope-refusal").count() == 0


class TestUserSearch:
    """The Users tab: every person who has logged in, filtered as you type on id OR display name.

    The same box as the Groups tab — same matcher, same bar, same focus and IME machinery — so the
    behaviour that matters is what is different: two fields, one of them nullable. "cooper" has to
    find alice, whose id says nothing of the kind, and gatekeeper, whose provider supplied no name,
    has to stay findable by id and render as a bare id. dave, a synced member who has never logged
    in, is NOT a row: he is the never-logged-in line (TestUsersTabLogins).
    """

    def _open(self, dash):
        dash.locator("button[data-nav='users']").click()
        # A DATA row, not the box: the tab paints before it fetches, so the box appears at once and
        # only a fetched render produces tr[data-user] — the same reason every tab helper waits this way.
        dash.wait_for_selector("tr[data-user]")

    def _ids(self, dash):
        return [r.split("\t")[0].split("·")[0].strip()
                for r in dash.locator("tbody tr").all_inner_texts()]

    def test_the_tab_lists_every_user_who_has_logged_in_with_a_group_count(self, dash):
        self._open(dash)
        assert self._ids(dash) == ["alice", "gatekeeper", "kubeadmin"], self._ids(dash)
        row = dash.locator("tr[data-user='alice']").inner_text()
        assert row.split("\t")[3].strip() == "2", row
        assert "3 shown" in dash.locator("section.card h2").first.inner_text()

    def test_a_single_term_matches_the_username(self, dash):
        self._open(dash)
        dash.fill("#f-user-search", "gate")
        dash.wait_for_function("() => view.userSearch === 'gate'")
        assert self._ids(dash) == ["gatekeeper"]

    def test_a_term_matches_the_full_name(self, dash):
        """The whole point: the reader knows the person, not the id."""
        self._open(dash)
        dash.fill("#f-user-search", "cooper")
        dash.wait_for_function("() => view.userSearch === 'cooper'")
        assert self._ids(dash) == ["alice"]
        assert "cooper" not in "alice", "the premise: the id alone would not have matched"

    def test_terms_are_ANDed_across_id_and_name_in_either_order(self, dash):
        self._open(dash)
        for query in ("alice cooper", "cooper alice"):
            dash.fill("#f-user-search", query)
            dash.wait_for_function(f"() => view.userSearch === {query!r}")
            assert self._ids(dash) == ["alice"], (query, self._ids(dash))

    def test_a_term_cannot_straddle_the_id_and_the_name(self, dash):
        """Fields are joined with a space, so "ecoop" (the end of alice + the start of Cooper) is no match."""
        self._open(dash)
        dash.fill("#f-user-search", "ecoop")
        dash.wait_for_function("() => view.userSearch === 'ecoop'")
        assert self._ids(dash) == []

    def test_it_is_case_insensitive(self, dash):
        self._open(dash)
        dash.fill("#f-user-search", "COOPER")
        dash.wait_for_function("() => view.userSearch === 'COOPER'")
        assert self._ids(dash) == ["alice"]

    def test_an_unnamed_user_renders_the_bare_id(self, dash):
        """A User whose provider supplied no name: the id is rendered unchanged — never a placeholder."""
        self._open(dash)
        assert "·" not in dash.locator("tr[data-user='gatekeeper']").inner_text().split("\t")[0]
        assert "· Alice Cooper" in dash.locator("tr[data-user='alice']").inner_text()

    def test_a_term_matching_nothing_says_the_search_is_hiding_them(self, dash):
        self._open(dash)
        dash.fill("#f-user-search", "zzzznope")
        dash.wait_for_function("() => view.userSearch === 'zzzznope'")
        body = dash.locator("section.card").first.inner_text()
        assert "No user id or name contains" in body, body[:200]
        assert "search hiding them" in body, body[:300]

    def test_the_header_reports_the_denominator_while_filtering(self, dash):
        self._open(dash)
        assert "of" not in dash.locator("section.card h2").first.inner_text()
        dash.fill("#f-user-search", "gate")
        dash.wait_for_function("() => view.userSearch === 'gate'")
        assert "1 of 3 shown" in dash.locator("section.card h2").first.inner_text()

    def test_escape_clears_it(self, dash):
        self._open(dash)
        dash.fill("#f-user-search", "gate")
        dash.wait_for_function("() => view.userSearch === 'gate'")
        dash.locator("#f-user-search").press("Escape")
        dash.wait_for_function("() => view.userSearch === ''")
        assert len(self._ids(dash)) == 3

    def test_the_caret_and_focus_survive_a_repaint(self, dash):
        """The shared machinery has to work for the SECOND box, not just the one it was written for."""
        self._open(dash)
        dash.fill("#f-user-search", "alice-cooper")
        dash.locator("#f-user-search").evaluate("el => el.setSelectionRange(5, 5)")
        dash.evaluate("() => render()")
        state = dash.evaluate("""() => {
            const el = document.getElementById('f-user-search');
            return { focused: document.activeElement === el, start: el.selectionStart, value: el.value };
        }""")
        assert state["focused"], "focus was lost when the filter bar re-rendered"
        assert state["start"] == 5, f"the caret moved to {state['start']}"
        assert state["value"] == "alice-cooper"

    def test_searching_does_not_refetch(self, dash):
        dash.evaluate("() => { window.__calls = 0; const f = window.fetch;"
                      " window.fetch = (...a) => { window.__calls++; return f(...a); }; }")
        self._open(dash)
        before = dash.evaluate("() => window.__calls")
        dash.fill("#f-user-search", "ali")
        dash.wait_for_function("() => view.userSearch === 'ali'")
        dash.wait_for_timeout(400)
        assert dash.evaluate("() => window.__calls") == before, "filtering issued a network request"

    def test_the_list_is_fetched_at_the_servers_maximum(self, dash):
        """The default limit (1,000) is below the reference cluster's 1,240 users; a default fetch would
        clip the list the box then searches, and a person past the cut would read as "no match"."""
        self._open(dash)
        limit = dash.evaluate("() => data.users.limit")
        assert limit == 10000, limit

    def test_a_filtered_row_drills_in_and_back_returns_to_the_tab(self, dash):
        self._open(dash)
        dash.fill("#f-user-search", "cooper")
        dash.wait_for_function("() => view.userSearch === 'cooper'")
        dash.locator("tr[data-user='alice']").click()
        dash.wait_for_selector("#back-groups")
        assert dash.evaluate("() => view.user") == "alice"
        assert dash.evaluate("() => view.page") == "users", "a drill from Users must stay under Users"
        assert "all users" in dash.locator("#back-groups").inner_text()
        dash.locator("#back-groups").click()
        dash.wait_for_selector("#f-user-search")
        assert dash.evaluate("() => view.page") == "users"
        # The filter is a filter, not a position: it survives the round trip, exactly as the group
        # box's does, so the reader lands back on the narrowed list they left.
        assert dash.evaluate("() => view.userSearch") == "cooper"
        assert self._ids(dash) == ["alice"]

    def test_the_box_only_exists_on_the_users_tab(self, dash):
        self._open(dash)
        assert dash.locator("#f-user-search").count() == 1
        assert dash.locator("#f-group-search").count() == 0
        dash.click('button.tab:text-is("Groups")')
        dash.wait_for_selector("tr[data-group]")
        assert dash.locator("#f-user-search").count() == 0
        assert dash.locator("#f-group-search").count() == 1
        dash.click('button.tab:text-is("Overview")')
        dash.wait_for_timeout(300)
        assert dash.locator("#f-user-search").count() == 0

    def test_the_visible_label_is_the_accessible_name(self, dash):
        self._open(dash)
        el = dash.locator("#f-user-search")
        assert el.get_attribute("aria-label") is None, "aria-label is overriding the visible label"
        assert el.get_attribute("aria-describedby") == "f-user-search-help"
        assert dash.locator("label[for='f-user-search']").inner_text().strip() == "Find"
        help_text = dash.locator("#f-user-search-help")
        assert "AND" in help_text.inner_text()
        assert help_text.evaluate("el => getComputedStyle(el).display") != "none"
        assert help_text.evaluate("el => el.getBoundingClientRect().width") <= 2

    def test_a_zero_denominator_does_not_blame_the_search(self, dash):
        """With nothing behind the search, "the search is hiding them" would be false."""
        self._open(dash)
        dash.evaluate("() => { data.users = { scope: 'all', users: [], truncated: false, limit: 10000 };"
                      " view.userSearch = 'x'; render(); }")
        body = dash.locator("section.card").first.inner_text()
        assert "search hiding" not in body, body
        assert "to see all 0" not in body, body
        assert "No one has logged in to this cluster yet" in body, body

    def test_a_truncated_list_says_so_and_the_empty_state_hedges(self, dash):
        """A capped list that looks complete is the failure the envelope's `truncated` exists to avoid."""
        self._open(dash)
        dash.evaluate("""() => {
            data.users = { scope: 'all', truncated: true, limit: 3, users: data.users.users };
            view.userSearch = ''; render();
        }""")
        note = dash.locator(".truncation-note").first.inner_text()
        assert "first 3" in note and "past the cut" in note, note
        dash.fill("#f-user-search", "zzz")
        dash.wait_for_function("() => view.userSearch === 'zzz'")
        body = dash.locator("section.card").first.inner_text()
        assert "search hiding them" in body and "past the cut" in body, body

    def test_the_paint_cap_is_stated_and_never_hides_a_match(self, dash):
        """Only the PAINT is capped; the match runs over every fetched row."""
        self._open(dash)
        dash.evaluate("""() => {
            const rows = [];
            for (let i = 0; i < 1500; i++) rows.push({ user_name: `u${String(i).padStart(4, '0')}`,
                full_name: i === 1499 ? 'Last Person' : null, group_count: 1,
                first_seen_at: '2026-01-01T00:00:00+00:00' });
            data.users = { scope: 'all', truncated: false, limit: 10000, users: rows };
            view.userSearch = ''; render();
        }""")
        assert dash.locator("tbody tr").count() == 1000
        note = dash.locator(".truncation-note").first.inner_text()
        assert "1000 of 1500 users painted" in note, note
        # The heading counts what is painted, not what matched — "1500 shown" over 1,000 rows was
        # the defect the adversarial review found.
        assert "1000 of 1500 shown" in dash.locator("section.card h2").first.inner_text()
        dash.fill("#f-user-search", "last person")
        dash.wait_for_function("() => view.userSearch === 'last person'")
        assert self._ids(dash) == ["u1499"], "the 1500th row was fetched, so it must be findable"
        assert dash.locator(".truncation-note").count() == 0

    def test_an_ime_composition_survives_its_own_input_events(self, dash):
        """The composing slot has to hold THIS box's id, not a flag written for the group box."""
        self._open(dash)
        dash.focus("#f-user-search")
        cdp = dash.context.new_cdp_session(dash)
        cdp.send("Input.imeSetComposition", {"text": "か", "selectionStart": 1, "selectionEnd": 1})
        dash.wait_for_timeout(100)
        cdp.send("Input.imeSetComposition", {"text": "かん", "selectionStart": 2, "selectionEnd": 2})
        dash.wait_for_timeout(100)
        cdp.send("Input.insertText", {"text": "かんり"})
        dash.wait_for_timeout(100)
        got = dash.evaluate("() => document.getElementById('f-user-search').value")
        assert got == "かんり", f"the composition was aborted by a repaint: {got!r}"
        assert dash.evaluate("() => view.userSearch") == "かんり"

    def test_the_headline_counts_people_who_have_logged_in_and_the_members_who_have_not(self, dash):
        """The number the operator asked for: how many people have logged in to the cluster."""
        self._open(dash)
        kpis = {k.split("\n")[0].strip(): k.split("\n")[1].strip()
                for k in dash.locator(".kpi").all_inner_texts() if "\n" in k}
        assert kpis["Have logged in"] == "3", kpis
        assert kpis["In a synced group"] == "2" and kpis["Logged in, no synced group"] == "1", kpis
        assert kpis["Synced, never logged in"] == "1", kpis

    def test_a_synced_member_who_never_logged_in_is_a_line_not_a_row(self, dash):
        """dave is in a synced group and has no User object. He is not a user of the cluster yet,
        so he is not counted — but a reviewer wants the number, and the name one click away."""
        self._open(dash)
        assert "dave" not in self._ids(dash)
        line = dash.locator("#never-logged-in")
        assert "1 synced member has never logged in" in line.inner_text()
        assert dash.locator("#never-logged-in [data-user='dave']").count() == 0, "names start hidden"
        dash.locator("#toggle-never-names").click()
        dash.wait_for_selector("#never-logged-in [data-user='dave']")
        dash.locator("#never-logged-in [data-user='dave']").click()
        dash.wait_for_selector("#back-groups")
        assert dash.evaluate("() => view.user") == "dave", "the name drills to his group page as usual"

    def test_a_user_in_no_synced_group_shows_zero_and_the_login_status(self, dash):
        self._open(dash)
        row = dash.locator("tr[data-user='kubeadmin']").inner_text().split("\t")
        assert row[3].strip() == "0", row
        assert "logged in since" in row[1], row
        assert row[2].strip() == "developer", row

    def test_chips_narrow_by_group_membership_and_by_provider(self, dash):
        self._open(dash)
        dash.locator("[data-ufilter='nogroup']").click()
        dash.wait_for_function("() => view.userFilter === 'nogroup'")
        assert self._ids(dash) == ["kubeadmin"]
        assert dash.locator("[data-ufilter='nogroup']").get_attribute("aria-pressed") == "true"
        dash.locator("[data-ufilter='provider:ldap-local']").click()
        dash.wait_for_function("() => view.userFilter === 'provider:ldap-local'")
        assert self._ids(dash) == ["alice", "gatekeeper"]
        assert "2 of 3 shown" in dash.locator("section.card h2").first.inner_text()
        dash.locator("[data-ufilter='all']").click()
        dash.wait_for_function("() => view.userFilter === 'all'")
        assert len(self._ids(dash)) == 3

    def test_a_chip_that_hides_everything_blames_the_chip_not_the_data(self, dash):
        self._open(dash)
        dash.evaluate("() => { view.userFilter = 'provider:nobody-uses-this'; render(); }")
        body = dash.locator("section.card").first.inner_text()
        assert "No user matches the selected chip" in body and "chip hiding them" in body, body
        dash.evaluate("() => { view.userFilter = 'all'; render(); }")

    def test_a_forbidden_source_is_named_by_grant_not_shown_as_an_empty_cluster(self, dash):
        """rbac.users off, or an image upgraded without the chart's RBAC: the poll still runs, and
        the tab must say what it cannot read rather than imply that nobody has logged in."""
        self._open(dash)
        dash.evaluate("() => { data.users = { scope: 'all', source: 'forbidden', users: [], total: 0,"
                      " truncated: false, limit: 10000, never_logged_in_members: { count: 0, names: [] } }; render(); }")
        body = dash.locator("#users-source-note").inner_text()
        assert "not permitted to list users.user.openshift.io" in body and "rbac.users" in body, body
        assert "No one has logged in" not in dash.locator("section.card").first.inner_text()

    def test_a_forbidden_source_with_stale_rows_keeps_them_and_says_they_are_stale(self, dash):
        """rbac.users revoked after a successful poll: the rows are last cycle's and must be labelled so."""
        self._open(dash)
        dash.evaluate("() => { data.users = Object.assign({}, data.users, { source: 'forbidden' }); render(); }")
        note = dash.locator("#users-source-note").inner_text()
        assert "not permitted to list users.user.openshift.io" in note and "from the last poll" in note, note
        assert dash.locator("tbody tr").count() == 3, "the stale rows stay on screen, labelled"
        dash.evaluate("() => refresh()")
        dash.wait_for_function("() => data.users && data.users.source === 'ok'")

    def test_the_headline_does_not_count_a_manual_account_as_a_login(self, dash):
        """A User object with no identity is a row, labelled, and not a login (Codex, #47)."""
        self._open(dash)
        dash.evaluate("""() => {
            const rows = data.users.users.concat([{ user_name: 'manual', full_name: null, group_count: 0,
                first_seen_at: null, logged_in: false, first_login_at: null, providers: [], last_login_at: null }]);
            data.users = Object.assign({}, data.users, { users: rows, total: 4, logged_in_total: 3 }); render();
        }""")
        kpis = {k.split("\n")[0].strip(): k.split("\n")[1].strip()
                for k in dash.locator(".kpi").all_inner_texts() if "\n" in k}
        assert kpis["Have logged in"] == "3" and kpis["Logged in, no synced group"] == "1", kpis
        assert "1 manual account" in dash.locator("#manual-accounts-note").inner_text()
        assert "manual account · never logged in" in dash.locator("tr[data-user='manual']").inner_text()
        dash.evaluate("() => refresh()")
        dash.wait_for_function("() => data.users && data.users.users.length === 3")

    def test_an_old_servers_payload_still_renders(self, dash):
        """Rows without the new fields and an envelope without total/source/login_capture/never line:
        the tab paints them as best it can and throws nowhere."""
        self._open(dash)
        dash.evaluate("""() => {
            data.users = { cluster: 'crc-local', scope: 'all', viewer: null, count: 2, truncated: false, limit: 10000,
                users: [{ user_name: 'old1', full_name: 'Old One', group_count: 1, first_seen_at: '2026-01-01T00:00:00+00:00' },
                        { user_name: 'old2', full_name: null, group_count: 2, first_seen_at: '2026-01-02T00:00:00+00:00' }] };
            render();
        }""")
        assert self._ids(dash) == ["old1", "old2"]
        assert dash.locator("#never-logged-in").count() == 0 and dash.locator("#users-source-note").count() == 0
        kpis = {k.split("\n")[0].strip(): k.split("\n")[1].strip()
                for k in dash.locator(".kpi").all_inner_texts() if "\n" in k}
        assert kpis["Have logged in"] == "2", kpis
        dash.evaluate("() => refresh()")
        dash.wait_for_selector("tr[data-user='alice']")

    def test_the_tab_states_when_its_source_was_last_read(self, dash):
        self._open(dash)
        age = dash.locator("#users-source-age").inner_text()
        assert "Users read from the cluster" in age and "ago" in age, age

    def test_a_cluster_switch_resets_the_chips_but_keeps_the_search(self, dash):
        """A provider chip names this cluster's providers; carried to another cluster it would hide
        every row for a reason the reader never chose. The search is a person and persists."""
        self._open(dash)
        dash.fill("#f-user-search", "ali")
        dash.wait_for_function("() => view.userSearch === 'ali'")
        dash.evaluate("() => { view.userFilter = 'provider:ldap-local'; view.showNeverNames = true; render(); }")
        dash.evaluate("() => { navigate({ cluster: 'prod-east', groupsync: null, group: null, user: null }); }")
        assert dash.evaluate("() => view.userFilter") == "all"
        assert dash.evaluate("() => view.showNeverNames") is False
        assert dash.evaluate("() => view.userSearch") == "ali"
        dash.evaluate("() => { navigate({ cluster: 'crc-local', groupsync: null, group: null, user: null }); view.userSearch = ''; refresh(); }")
        dash.wait_for_selector("tr[data-user='alice']")

    def test_the_detail_page_carries_the_login_facts(self, dash):
        self._open(dash)
        dash.locator("tr[data-user='kubeadmin']").click()
        dash.wait_for_selector("#back-groups")
        kpis = {k.split("\n")[0].strip(): k.split("\n")[1].strip()
                for k in dash.locator(".kpi").all_inner_texts() if "\n" in k}
        assert kpis["Groups"] == "0" and kpis["Logged in"] == "yes", kpis
        assert "First login" in kpis and "Last captured login" in kpis, kpis
        body = dash.locator("#main").inner_text()
        assert "never been in a synced group" in body, "a User in no group must not be told they lost groups"
        assert "were in at least one before" not in body
        dash.locator("#back-groups").click()
        dash.wait_for_selector("#f-user-search")

    def test_a_refused_list_is_a_named_refusal_not_an_empty_table(self, dash):
        """The endpoint 403s a reader with no verified identity; the tab must say so, not show nothing."""
        self._open(dash)
        dash.evaluate("() => { data.users = { forbidden: true }; render(); }")
        assert dash.locator(".scope-refusal").count() == 1
        body = dash.locator("#main").inner_text()
        assert "Withheld, not empty" in body and "Users" in body, body[:200]
        assert dash.locator("tr[data-user]").count() == 0

    def test_a_cluster_switch_drops_the_list(self, dash):
        """The rows belong to a cluster; painting them under another cluster's title would be a lie."""
        self._open(dash)
        assert dash.evaluate("() => data.users !== null")
        dash.evaluate("() => { navigate({ cluster: 'prod-east', groupsync: null, group: null, user: null }); }")
        assert dash.evaluate("() => data.users") is None
        assert dash.evaluate("() => view.cluster") == "prod-east"

    def test_a_changed_user_list_repaints_on_the_poll(self, dash):
        """The auto-refresh skips the repaint when nothing it fetched changed, judged by a
        fingerprint of the payloads. A payload left out of it is a change silently suppressed."""
        self._open(dash)
        before = dash.evaluate("() => document.querySelectorAll('tr[data-user]').length")
        dash.route("**/users?*", lambda route: route.fulfill(
            status=200, content_type="application/json",
            body='{"cluster":"crc-local","scope":"all","viewer":null,"count":1,"truncated":false,'
                 '"limit":10000,"users":[{"user_name":"zed","full_name":null,"group_count":1,'
                 '"first_seen_at":"2026-01-01T00:00:00+00:00"}]}'))
        dash.evaluate("() => refresh({ auto: true })")
        dash.wait_for_selector("tr[data-user='zed']", timeout=10_000)
        assert before == 3 and self._ids(dash) == ["zed"]

    def test_a_pasted_position_with_a_group_name_still_loads_the_list(self, dash):
        """No tab builds page=users together with a group, but a hash can carry both. The fetch
        must follow what render() paints — the list — or the tab loads forever (Cursor finding)."""
        dash.evaluate("() => { navigate({ page: 'users', group: 'app-ocp-rbac-alpha-ns-admin',"
                      " user: null }); render(); refresh(); }")
        dash.wait_for_selector("tr[data-user]", timeout=10_000)
        assert dash.evaluate("() => data.users !== null")
        assert len(self._ids(dash)) == 3

    def test_other_tabs_never_request_the_user_list(self, dash):
        """Fetched only on its own tab, like logins: the other pages must not pay for a 10,000-row list."""
        dash.evaluate("() => { window.__urls = []; const f = window.fetch;"
                      " window.fetch = (...a) => { window.__urls.push(String(a[0])); return f(...a); }; }")
        for tab in ("Groups", "Overview", "Access granted", "RBAC policy", "Namespace audit", "Logins", "Usage"):
            dash.click(f'button.tab:text-is("{tab}")')
            dash.wait_for_function("() => !document.querySelector('#main .empty-note') || "
                                   "!/Loading/.test(document.querySelector('#main .empty-note').textContent)",
                                   timeout=10_000)
        urls = dash.evaluate("() => window.__urls")
        assert not [u for u in urls if u.endswith("/users") or "/users?" in u], urls
        self._open(dash)
        urls = dash.evaluate("() => window.__urls")
        assert [u for u in urls if "/users?" in u], "the Users tab itself must fetch the list"


class TestAccessGrantedSelfTier:
    """A narrowed reader's Access granted tab: their own path, not the refusal. The endpoint the
    administrator view reads still 403s at self (test_view_scoping pins the body); the tab reads
    the reader's own /users/{me} instead, which the gate never withheld."""

    def _open(self, page, base, user):
        p = _open_as(page, base, user)
        p.locator("button[data-nav='bindings']").click()
        p.wait_for_function("() => document.querySelector('#main .empty-note') === null"
                            " || !/Loading/.test(document.querySelector('#main .empty-note').textContent)",
                            timeout=10_000)
        return p

    def test_a_member_sees_the_bindings_that_reach_them_and_no_refusal(self, page, scoped_server):
        p = self._open(page, scoped_server, "alice")
        p.wait_for_selector(".scope-banner")
        assert p.locator(".scope-refusal").count() == 0
        body = p.locator("#main").inner_text()
        assert "reaches alice" in body, body[:300]
        assert "managed-admin-rb" in body and "hand-made-crb" in body, body[:400]
        assert "app-ocp-rbac-alpha-ns-admin" in body
        assert "For administrators only" not in body and "Dashboard API error" not in body
        assert p.locator("#f-binding").count() == 0 and p.locator("#f-binding-search").count() == 0

    def test_a_reader_in_no_group_gets_the_empty_state_not_an_error(self, page, scoped_server):
        p = self._open(page, scoped_server, "nomember")
        p.wait_for_selector("#main .empty-note")
        body = p.locator("#main").inner_text()
        assert "No group grants you access" in body and "nomember" in body, body[:300]
        assert "Dashboard API error" not in body and "For administrators only" not in body

    def test_the_administrator_still_sees_the_whole_cluster(self, page, scoped_server):
        p = self._open(page, scoped_server, "root")
        p.wait_for_selector("text=grant nobody")
        assert p.locator(".scope-banner").count() == 0
        assert p.locator("section.card:has(h2:has-text('Granted')) tbody tr").count() >= 1
        assert p.locator("#f-binding").count() == 1

    def test_a_known_narrowed_reader_never_requests_the_findings(self, page, scoped_server):
        """Once the tier is known, the tab fetches only the reader's own path: a findings request
        would only come back as the designed 403 and count as a refusal on /metrics every cycle."""
        p = self._open(page, scoped_server, "alice")
        p.wait_for_selector(".scope-banner")
        p.evaluate("() => { window.__urls = []; const f = window.fetch;"
                   " window.fetch = (...a) => { window.__urls.push(String(a[0])); return f(...a); }; }")
        p.evaluate("() => refresh()")
        p.wait_for_function("() => window.__urls.some((u) => u.includes('/users/alice'))", timeout=10_000)
        p.wait_for_timeout(300)
        urls = p.evaluate("() => window.__urls")
        assert not [u for u in urls if "bindings/findings" in u], urls
        assert [u for u in urls if u.endswith("/users/alice")], urls

    def test_a_reader_promoted_mid_session_sees_the_cluster_on_the_next_refresh(self, page, scoped_server):
        """The tier used to be decided from the PREVIOUS cycle's identity: a promotion showed the
        old narrowed view for a cycle (Codex, #48). The tab now decides from the whoami that just
        arrived and makes one guarded follow-up fetch."""
        p = self._open(page, scoped_server, "alice")
        p.wait_for_selector(".scope-banner")
        p.set_extra_http_headers({"X-Forwarded-User": "root"})
        p.evaluate("() => refresh()")
        p.wait_for_selector("text=grant nobody", timeout=10_000)
        assert p.locator(".scope-banner").count() == 0
        assert p.locator("section.card:has(h2:has-text('Granted')) tbody tr").count() >= 1
        assert p.evaluate("() => data.myAccess") is None, "the narrowed payload is not left behind"

    def test_a_reader_demoted_mid_session_sees_their_own_path_on_the_next_refresh(self, page, scoped_server):
        p = self._open(page, scoped_server, "root")
        p.wait_for_selector("text=grant nobody")
        p.set_extra_http_headers({"X-Forwarded-User": "alice"})
        p.evaluate("() => refresh()")
        p.wait_for_selector(".scope-banner", timeout=10_000)
        body = p.locator("#main").inner_text()
        assert "reaches alice" in body and "grant nobody" not in body, body[:300]
        assert p.evaluate("() => data.findings") is None, "the wide payload is not this reader's to paint"

    def test_a_session_that_changes_hands_refetches_the_new_readers_own_path(self, page, scoped_server):
        """Codex, C1 review, routed to SPEC_D2: refresh() made its speculative own-path request for
        the PREVIOUS cycle's viewer, so when Alice's tab became Bob's session the request was
        /users/alice as Bob — a 403 that rejected the shared Promise.all and left the generic API
        error card until a reload. The speculative call now resolves that 403 to null, and the
        follow-up fetches whoever whoami names."""
        p = self._open(page, scoped_server, "alice")
        p.wait_for_selector(".scope-banner")
        assert "reaches alice" in p.locator("#main").inner_text()
        p.set_extra_http_headers({"X-Forwarded-User": "bob"})
        p.evaluate("() => refresh()")
        p.wait_for_function("() => data.myAccess && data.myAccess.viewer === 'bob'", timeout=10_000)
        body = p.locator("#main").inner_text()
        assert "Dashboard API error" not in body, body[:300]
        assert "reaches alice" not in body, body[:300]
        assert p.evaluate("() => data.findings") is None
        assert p.evaluate("() => data.whoami.user") == "bob"

    def test_a_silent_selected_cluster_scope_stays_narrowed_in_the_pill(self, page, scoped_server):
        """Codex, review D2: the pill tested `=== "self"` while every narrowing helper tests
        `!== "all"`, so a missing or junk scope painted "Full view" above a layout that stayed
        narrowed. Same fail-closed rule everywhere now."""
        p = _open_as(page, scoped_server, "alice")
        p.wait_for_selector("#scope-pill:not([hidden])")
        p.evaluate("""() => {
          delete data.whoami.visibility.scope;
          const c = data.whoami.visibility.clusters;
          if (c && view.cluster && c[view.cluster]) delete c[view.cluster].scope;
          render();
        }""")
        assert p.evaluate("() => narrowedReader()") is True
        assert p.locator("#scope-pill").inner_text().startswith("Your view")
        assert "self" in (p.locator("#scope-pill").get_attribute("class") or "")

    def test_the_selector_stays_narrowed_when_the_row_scope_is_silent(self, page, scoped_server):
        """Cursor, second pass: the selector still tested `=== "self"` after the pill moved to
        `!== "all"` — a silent row scope dropped " — your view" while the page stayed narrowed."""
        p = _open_as(page, scoped_server, "alice")
        p.wait_for_selector("#f-cluster")
        p.evaluate("""() => {
          (data.clusters || []).forEach((c) => { c.visibility = Object.assign({}, c.visibility || {}, { scope: undefined }); });
          render();
        }""")
        assert "your view" in p.locator("#f-cluster").inner_text()

    def test_reports_refresh_fetches_on_the_hosts_headline(self, page, scoped_server):
        """Cursor, second pass: the Reports test asserted reportsPage() only, so the catalogue
        fetch guard in refresh() could drift back to the selected cluster and paint a form that
        never loads. Both guards read the host's headline."""
        p = _open_as(page, scoped_server, "root")
        src = p.evaluate("() => refresh.toString()")
        assert 'view.page === "reports" && reportingEnabled() && !narrowedOnHost()' in src
        assert 'view.page === "reports" && reportingEnabled() && !narrowedReader()' not in src

    def test_reports_catch_up_on_the_refresh_that_promotes_the_host_tier(self, page, scoped_server):
        """Codex, review D2 second pass: refresh() chose its report requests on the PREVIOUS
        cycle's host tier, so a reader promoted mid-session saw "Loading…" for a whole cycle
        (measured: zero report calls on the promoting refresh). The same catch-up as the Access
        granted tab: reconcile against the whoami that just arrived."""
        p = _open_as(page, scoped_server, "alice")
        p.evaluate("""() => {
          view.page = "reports";
          data.version.features.reporting = true;
          data.reportCatalog = null; data.reportRuns = null;
          window.__reportGets = [];
          window.reportGet = async (path) => { window.__reportGets.push(path); return path === "/api/reports" ? { reports: [] } : { runs: [] }; };
          render();
        }""")
        assert p.evaluate("() => narrowedOnHost()") is True
        p.set_extra_http_headers({"X-Forwarded-User": "root"})
        p.evaluate("() => refresh()")
        p.wait_for_function("() => data.whoami && data.whoami.visibility && data.whoami.visibility.scope === 'all'", timeout=10_000)
        p.wait_for_function("() => window.__reportGets.length >= 2", timeout=10_000)
        assert p.evaluate("() => window.__reportGets") == ["/api/reports", "/api/runs?limit=50"]
        assert p.evaluate("() => data.reportCatalog !== null") is True

    def test_reports_follow_the_hosts_headline_not_the_selected_remote(self, page, scoped_server):
        """Cursor, review D2: reports are documents over the whole snapshot, minted on the host's
        tier by /api/report/ticket; the tab read the SELECTED cluster's decision, so a host
        administrator with a narrowed remote selected was refused a report the API would mint."""
        p = _open_as(page, scoped_server, "root")
        p.evaluate("""() => {
          data.whoami.visibility.clusters = Object.assign({}, data.whoami.visibility.clusters,
            { east: { policy: "self-only", identity: "none", scope: "self" } });
          data.clusters = (data.clusters || []).concat([{ id: "east", visibility: { policy: "self-only", scope: "self" } }]);
          view.cluster = "east";
          render();
        }""")
        assert p.evaluate("() => narrowedReader()") is True, "the selected remote is narrowed for root"
        assert p.evaluate("() => narrowedOnHost()") is False, "root is wide on the host"
        assert p.evaluate("() => reportsPage().includes('scope-refusal')") is False, \
            "the Reports tab must not refuse a host administrator over the selected remote"

    def test_an_unknown_tier_paints_neither_tiers_payload(self, page, scoped_server):
        """A whoami that fails on a later cycle leaves the tier indeterminate. The cached wide
        payload is not the reader's to see then, and the own path is not a claim either: the tab
        fails closed to Loading, as the Overview does (Codex second pass)."""
        p = self._open(page, scoped_server, "root")
        p.wait_for_selector("text=grant nobody")
        p.evaluate("() => { data.whoami = null; render(); }")
        body = p.locator("#main").inner_text()
        assert "Loading" in body and "grant nobody" not in body and "Granted" not in body, body[:200]
        assert p.locator(".drill").count() == 0
        p.evaluate("() => refresh()")
        p.wait_for_selector("text=grant nobody", timeout=10_000)

    def test_a_narrowed_identity_with_no_username_is_a_named_card_not_loading(self, page, scoped_server):
        p = self._open(page, scoped_server, "alice")
        p.wait_for_selector(".scope-banner")
        p.evaluate("() => { data.whoami = Object.assign({}, data.whoami, { user: null }); data.myAccess = null; render(); }")
        body = p.locator("#main").inner_text()
        assert "passed no username" in body and "Loading" not in body, body[:300]
        assert p.locator(".scope-refusal").count() == 1

    def test_a_non_404_failure_on_the_own_path_is_still_an_error(self, page, scoped_server):
        p = self._open(page, scoped_server, "alice")
        p.wait_for_selector(".scope-banner")
        p.route("**/users/alice", lambda route: route.fulfill(status=500, content_type="application/json", body='{"detail":"boom"}'))
        p.evaluate("() => { data.myAccess = null; refresh(); }")
        p.wait_for_function("() => /Dashboard API error/.test(document.querySelector('#main').innerText)", timeout=10_000)
        p.unroute("**/users/alice")

    def test_the_via_group_drills_to_the_readers_own_group(self, page, scoped_server):
        p = self._open(page, scoped_server, "alice")
        p.wait_for_selector("[data-group='app-ocp-rbac-alpha-ns-admin']")
        p.locator("[data-group='app-ocp-rbac-alpha-ns-admin']").first.click()
        p.wait_for_function("() => view.group === 'app-ocp-rbac-alpha-ns-admin'")
        assert p.evaluate("() => view.page") == "groups"


class TestUserSearchVisibility:
    """The Users tab under view restrictions: own row at the narrowed tier, said in words."""

    def _open(self, page, base, user):
        p = _open_as(page, base, user)
        p.locator("button[data-nav='users']").click()
        p.wait_for_function("() => data.users !== null")
        return p

    def test_self_tier_shows_only_your_own_row_and_says_so(self, page, scoped_server):
        p = self._open(page, scoped_server, "alice")
        p.wait_for_selector("tr[data-user='alice']")
        assert p.locator("tbody tr").count() == 1
        banner = p.locator(".scope-banner").inner_text()
        assert "alice" in banner and "own row" in banner, banner
        assert p.locator("#scope-pill").inner_text().startswith("Your view")
        assert "Alice Cooper" in p.locator("tr[data-user='alice']").inner_text()

    def test_self_tier_with_no_membership_is_not_an_empty_cluster(self, page, scoped_server):
        p = self._open(page, scoped_server, "nomember")
        p.wait_for_selector("#main .empty-note")
        body = p.locator("#main").inner_text()
        assert "nomember" in body and "not a statement that nobody has logged in" in body, body
        assert "No one has logged in" not in body, body

    def test_self_tier_never_logged_in_line_names_nobody_else(self, page, scoped_server):
        """dave has never logged in; at his own tier he learns that about himself and nothing about
        anyone else — no toggle, no other names, no cluster-wide KPIs."""
        p = self._open(page, scoped_server, "dave")
        p.wait_for_selector("#never-logged-in")
        line = p.locator("#never-logged-in").inner_text()
        assert "1 synced member has never logged in" in line, line
        assert p.locator("#toggle-never-names").count() == 0
        assert p.locator(".kpi").count() == 0, "cluster-wide counts are the administrator tier"
        body = p.locator("#main").inner_text()
        for other in ("alice", "gatekeeper", "kubeadmin"):
            assert other not in body, other

    def test_the_administrator_sees_every_user_and_no_banner(self, page, scoped_server):
        p = self._open(page, scoped_server, "root")
        p.wait_for_selector("tr[data-user='kubeadmin']")
        assert p.locator("tbody tr").count() == 3
        assert p.locator(".scope-banner").count() == 0


class TestMemberSearch:
    """The Find member box on a group's detail page: the third box on the shared machinery, and the
    one with per-group state — a filter typed against one group must not follow the reader to the next."""

    GROUP = "app-ocp-rbac-alpha-ns-admin"

    def _open(self, dash, name=GROUP):
        dash.locator("button[data-nav='groups']").click()
        dash.wait_for_selector("tr[data-group]")
        dash.locator(f"tr[data-group='{name}']").click()
        dash.wait_for_selector("#back-groups")
        dash.wait_for_selector("#f-member-search")

    def _members(self, dash):
        return dash.evaluate("() => Array.from(document.querySelectorAll('tr[data-user]'))"
                             ".map(r => r.dataset.user)")

    def _members_card(self, dash):
        return dash.locator("section.card").nth(1).inner_text()

    def test_a_term_matches_the_username(self, dash):
        self._open(dash)
        before = self._members(dash)
        assert "dave" in before and "alice" in before, before
        dash.fill("#f-member-search", "dave")
        dash.wait_for_function("() => view.memberSearch === 'dave'")
        assert self._members(dash) == ["dave"]

    def test_a_term_matches_the_full_name(self, dash):
        self._open(dash)
        dash.fill("#f-member-search", "cooper")
        dash.wait_for_function("() => view.memberSearch === 'cooper'")
        assert self._members(dash) == ["alice"]

    def test_the_header_reports_the_denominator(self, dash):
        self._open(dash)
        total = len(self._members(dash))
        dash.fill("#f-member-search", "dave")
        dash.wait_for_function("() => view.memberSearch === 'dave'")
        assert f"1 of {total} shown" in self._members_card(dash)

    def test_nothing_matching_blames_the_search_not_the_group(self, dash):
        self._open(dash)
        dash.fill("#f-member-search", "zzzznope")
        dash.wait_for_function("() => view.memberSearch === 'zzzznope'")
        card = self._members_card(dash)
        assert "No member's id or name contains" in card and "search hiding them" in card, card
        assert "no members" not in card, card

    def test_an_empty_group_still_says_it_has_no_members(self, dash):
        """Zero denominator: the group is empty whatever is typed, and the box must not offer "see all 0"."""
        self._open(dash, "app-ocp-rbac-abcd-ns-superuser")
        dash.fill("#f-member-search", "x")
        dash.wait_for_function("() => view.memberSearch === 'x'")
        card = self._members_card(dash)
        assert "no members" in card, card
        assert "search hiding" not in card and "to see all 0" not in card, card

    def test_the_filter_clears_when_another_group_is_opened(self, dash):
        self._open(dash)
        dash.fill("#f-member-search", "dave")
        dash.wait_for_function("() => view.memberSearch === 'dave'")
        dash.evaluate("() => { navigate({ group: 'app-ssb-autobahnusers' }); refresh(); }")
        # The state clears at navigate(); the BOX clears when the fetched page paints, so wait for
        # the new group's payload before reading the DOM — the same paint-after-fetch as a real drill.
        dash.wait_for_function("() => data.group && data.group.name === 'app-ssb-autobahnusers'")
        assert dash.evaluate("() => view.memberSearch") == ""
        assert dash.locator("#f-member-search").input_value() == ""

    def test_the_filter_clears_on_the_way_back_to_the_list(self, dash):
        self._open(dash)
        dash.fill("#f-member-search", "dave")
        dash.wait_for_function("() => view.memberSearch === 'dave'")
        dash.locator("#back-groups").click()
        dash.wait_for_selector("tr[data-group]")
        assert dash.evaluate("() => view.memberSearch") == ""

    def test_the_filter_survives_the_poll_repaint(self, dash):
        """The poll never touches position, so a repaint keeps the filter AND the caret."""
        self._open(dash)
        dash.fill("#f-member-search", "dave")
        dash.wait_for_function("() => view.memberSearch === 'dave'")
        dash.evaluate("() => render()")
        assert dash.evaluate("() => view.memberSearch") == "dave"
        assert dash.evaluate("() => document.activeElement === document.getElementById('f-member-search')")
        assert self._members(dash) == ["dave"]

    def test_the_box_is_absent_on_the_group_list_and_the_user_page(self, dash):
        self._open(dash)
        assert dash.locator("#f-group-search").count() == 0, "the group box filters nothing here"
        dash.locator("tr[data-user='alice']").click()
        # The user PAGE, not #back-groups, which the group page already shows: a drill paints
        # after its fetch, so the bar is only re-rendered once the user payload lands.
        dash.wait_for_function("() => data.user && data.user.user === 'alice'")
        assert dash.locator("#f-member-search").count() == 0
        dash.locator("button[data-nav='groups']").click()
        dash.wait_for_selector("tr[data-group]")
        assert dash.locator("#f-member-search").count() == 0
        assert dash.locator("#f-group-search").count() == 1

    def test_escape_clears_it(self, dash):
        self._open(dash)
        dash.fill("#f-member-search", "dave")
        dash.wait_for_function("() => view.memberSearch === 'dave'")
        dash.locator("#f-member-search").press("Escape")
        dash.wait_for_function("() => view.memberSearch === ''")
        assert len(self._members(dash)) > 1

    def test_the_visible_label_is_the_accessible_name(self, dash):
        self._open(dash)
        el = dash.locator("#f-member-search")
        assert el.get_attribute("aria-label") is None
        assert el.get_attribute("aria-describedby") == "f-member-search-help"
        assert dash.locator("label[for='f-member-search']").inner_text().strip() == "Find member"
        help_text = dash.locator("#f-member-search-help")
        assert "AND" in help_text.inner_text()
        assert help_text.evaluate("el => el.getBoundingClientRect().width") <= 2

    def test_a_filtered_member_still_drills_in(self, dash):
        self._open(dash)
        dash.fill("#f-member-search", "cooper")
        dash.wait_for_function("() => view.memberSearch === 'cooper'")
        dash.locator("tr[data-user='alice']").click()
        dash.wait_for_function("() => view.user === 'alice'")
        assert dash.evaluate("() => view.page") == "groups"


@pytest.fixture(scope="module")
def cliff_server(tmp_path_factory):
    """Its own store: one active cliff and one silenced, so the Overview's two renderings can
    be asserted without changing the shared seed's alert list."""
    db = str(tmp_path_factory.mktemp("gsd") / "cliff.db")
    now = datetime.now(UTC)
    store = Store(db)
    store.upsert_cluster("crc-local", "https://api.crc.testing:6443", True)
    store.record_poll("crc-local", "ok", None)
    store.sync_members("crc-local", {"app-ocp-rbac-loud-ns-view": [f"u{i}" for i in range(20)],
                                     "app-ocp-rbac-quiet-ns-view": [f"v{i}" for i in range(20)]},
                       {}, "2026-01-01T00:00:00Z")
    store.sync_members("crc-local", {"app-ocp-rbac-loud-ns-view": ["u0"],
                                     "app-ocp-rbac-quiet-ns-view": ["v0"]}, {}, _iso(now))
    store.replace_group_state("crc-local", [
        {"name": "app-ocp-rbac-loud-ns-view", "member_count": 1, "sync_provider": "gs_ldap",
         "group_synced_at": None, "ldap_uid": None},
        {"name": "app-ocp-rbac-quiet-ns-view", "member_count": 1, "sync_provider": "gs_ldap",
         "group_synced_at": None, "ldap_uid": None, "cliff_silence": "until=2099-01-01"},
    ], _iso(now))
    store.close()
    settings = Settings(clusters=[ClusterConfig("crc-local", "https://api.crc.testing:6443", token_env="X")],
                        db_path=db, view_restrictions_enabled=False)
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(build_app(settings, run_poller=False), host="127.0.0.1",
                                        port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(f"{base}/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    yield base
    srv.should_exit = True
    thread.join(timeout=5)


class TestGroupCountCliffOnTheOverview:
    def test_silenced_is_shown_dimmed_and_counted_apart(self, page, cliff_server):
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{cliff_server}/#page=overview")
        page.wait_for_selector(".alert-row", timeout=10_000)
        assert not errors, errors
        rows = page.locator(".alert-row")
        silenced = page.locator(".alert-row.silenced")
        assert silenced.count() == 1
        assert "app-ocp-rbac-quiet-ns-view" in silenced.first.inner_text()
        assert "silenced by annotation" in silenced.first.locator(".silence-tag").inner_text()
        # The active cliff has no tag and the hero counts it alone (2 empty_group rows are
        # also active: both groups now have one member, not zero — so exactly 1 active row).
        active_rows = [rows.nth(i).inner_text() for i in range(rows.count())
                       if "silenced by" not in rows.nth(i).inner_text()]
        assert any("app-ocp-rbac-loud-ns-view" in t for t in active_rows)
        assert page.locator(".hero .value").first.inner_text().strip() == str(len(active_rows))
        assert "1 silenced" in page.locator(".hero .label").first.inner_text()
        labels = {page.locator(".alert-row .badge").nth(i).inner_text().strip()
                  for i in range(page.locator(".alert-row .badge").count())}
        assert labels <= {"critical", "warning"}, "silenced is a tag, not a severity"


class TestExport:
    """CSV/JSON export of the table on screen (docs/DESIGN_export.md).

    The file is built in the browser from `data`, so what these prove is the correspondence:
    the download holds exactly the rows the table shows, after the filter and sort, says when
    the page was a cut of a larger set, and never makes a request.
    """

    def _users(self, dash):
        dash.locator("button[data-nav='users']").click()
        dash.wait_for_selector("tr[data-user]")
        dash.wait_for_selector("#export-csv")

    @staticmethod
    def _csv_rows(download):
        import csv
        import io
        raw = open(download.path(), "rb").read()
        assert raw.startswith("\ufeff".encode("utf-8")), "the CSV must carry the UTF-8 BOM"
        text = raw.decode("utf-8-sig")
        assert "\r\n" in text, "records end in CRLF (RFC 4180)"
        return list(csv.reader(io.StringIO(text, newline="")))

    def test_the_control_is_absent_when_the_module_is_off(self, page, quiet_server):
        page.goto(quiet_server + "#page=users&cluster=crc-local")
        page.wait_for_selector("tr[data-user]")
        assert page.locator("#export-csv").count() == 0
        assert page.evaluate("() => data.version.features.export") is False

    def test_the_buttons_are_real_buttons_in_the_filter_bar_and_keep_focus_across_the_poll(self, dash):
        self._users(dash)
        el = dash.locator("#filters #export-csv")
        assert el.evaluate("el => el.tagName") == "BUTTON"
        dash.focus("#export-csv")
        dash.evaluate("() => render()")  # the 60s poll
        assert dash.evaluate("() => document.activeElement.id") == "export-csv"

    def test_the_csv_holds_the_rows_shown_with_the_declared_columns(self, dash):
        self._users(dash)
        with dash.expect_download() as dl:
            dash.click("#export-csv")
        rows = self._csv_rows(dl.value)
        assert rows[0] == ["user_name", "full_name", "logged_in", "first_login_at", "first_login_source",
                           "providers", "group_count", "last_login_at", "first_seen_at"]
        assert [r[0] for r in rows[1:]] == ["alice", "gatekeeper", "kubeadmin"]
        assert rows[1][1] == "Alice Cooper" and rows[2][1] == ""
        import re
        assert re.fullmatch(r"gsd_crc-local_users_\d{8}T\d{6}Z\.csv", dl.value.suggested_filename)

    def test_the_export_follows_the_filter_and_the_chip(self, dash):
        self._users(dash)
        dash.fill("#f-user-search", "gate")
        dash.wait_for_function("() => view.userSearch === 'gate'")
        assert "1 row" in dash.locator("#export-note").inner_text()
        with dash.expect_download() as dl:
            dash.click("#export-json")
        import json
        doc = json.load(open(dl.value.path()))
        assert [r["user_name"] for r in doc["rows"]] == ["gatekeeper"]
        assert doc["filter"] == {"search": "gate", "chip": "all"}
        assert doc["scope"] == "all" and doc["truncated"] is False and doc["count"] == 1
        assert doc["cluster"] == "crc-local" and doc["tab"] == "users"
        assert set(doc["rows"][0]) == set(doc["columns"])
        dash.locator("#f-user-search").press("Escape")

    def test_a_partial_page_is_said_in_the_note_the_filename_and_the_json(self, dash):
        self._users(dash)
        dash.evaluate("() => { data.users = Object.assign({}, data.users, { truncated: true, total: 50 }); render(); }")
        note = dash.locator("#export-note")
        assert "partial" in note.inner_text() and "3 of 50" in note.inner_text()
        assert "partial" in (note.get_attribute("class") or "")
        with dash.expect_download() as dl:
            dash.click("#export-json")
        assert "_partial_" in dl.value.suggested_filename
        import json
        doc = json.load(open(dl.value.path()))
        assert doc["truncated"] is True and doc["served"] == 3 and doc["total"] == 50
        assert "partial" in doc["note"]
        dash.evaluate("() => refresh()")
        dash.wait_for_function("() => data.users && data.users.truncated === false")

    def test_the_csv_helper_quotes_per_rfc_4180_and_neutralises_formulas(self, dash):
        """The helper, exercised directly: the one place quoting lives."""
        got = dash.evaluate("""() => toCsv(["a", "b"], [
            { a: "x,y", b: 'he said "hi"' },
            { a: "line\\nbreak", b: null },
            { a: "=SUM(1)", b: ["p", "q"] },
            { a: 3, b: true },
        ])""")
        assert got == ("\ufeffa,b\r\n"
                       '"x,y","he said ""hi"""\r\n'
                       '"line\nbreak",\r\n'
                       "'=SUM(1),p; q\r\n"
                       "3,true\r\n")

    def test_access_granted_exports_the_visible_sections_in_page_order_and_sort(self, dash):
        dash.locator("button[data-nav='bindings']").click()
        dash.wait_for_selector("text=grant nobody")
        dash.wait_for_selector("#export-csv")
        with dash.expect_download() as dl:
            dash.click("#export-csv")
        rows = self._csv_rows(dl.value)
        assert rows[0][0] == "finding"
        findings = [r[0] for r in rows[1:]]
        # The default view paints dangling, unresolved, unmanaged, then granted — never built-in.
        assert "built_in" not in findings
        assert findings == sorted(findings, key=["dangling", "unresolved", "unmanaged", "ok"].index)
        assert dl.value.suggested_filename.startswith("gsd_crc-local_access-granted_")

    def test_a_long_cluster_id_still_produces_a_portable_filename(self, dash):
        """Review pass 2 (Codex): config.py accepts a 300-character cluster id and NAME_MAX is 255;
        the name is bounded and two ids sharing a prefix stay distinct."""
        self._users(dash)
        names = dash.evaluate("""() => {
            const desc = exportDescriptor(); const old = view.cluster;
            try {
              return ["x".repeat(300) + "a", "x".repeat(300) + "b"].map((c) => { view.cluster = c; return exportFilename(desc, "json"); });
            } finally { view.cluster = old; }
        }""")
        import re
        for name in names:
            assert len(name.encode("ascii")) <= 255
            assert re.fullmatch(r"[A-Za-z0-9._-]+", name)
        assert names[0] != names[1], "truncation must not collide cluster ids that share a prefix"

    def test_wide_access_json_names_section_then_column_sort(self, dash):
        """Review pass 2 (Cursor): the file is dangling, unresolved, unmanaged, ok — each sorted by the
        column — so the envelope must not claim a global column sort."""
        dash.locator("button[data-nav='bindings']").click()
        dash.wait_for_selector("text=grant nobody")
        dash.wait_for_selector("#export-json")
        with dash.expect_download() as dl:
            dash.click("#export-json")
        import json
        doc = json.load(open(dl.value.path()))
        assert doc["sort"] == {"key": "finding,group", "dir": "asc"}
        findings = [r["finding"] for r in doc["rows"]]
        assert findings == sorted(findings, key=["dangling", "unresolved", "unmanaged", "ok"].index)

    def test_the_export_makes_no_request(self, dash):
        self._users(dash)
        dash.evaluate("() => { window.__calls = 0; const f = window.fetch;"
                      " window.fetch = (...a) => { window.__calls++; return f(...a); }; }")
        with dash.expect_download():
            dash.click("#export-csv")
        # The download finishing is the end of the client work; any request the export made would
        # already have counted inside expect_download, so there is nothing to wait for.
        assert dash.evaluate("() => window.__calls") == 0

    def test_no_control_on_a_drill_down_or_a_loading_page(self, dash):
        self._users(dash)
        dash.locator("tr[data-user='alice']").click()
        dash.wait_for_selector("#back-groups")
        assert dash.locator("#export-csv").count() == 0
        dash.locator("#back-groups").click()
        dash.wait_for_selector("#export-csv")

    def test_no_control_while_the_bindings_tier_is_unknown(self, dash):
        """Review (Cursor): the page paints Loading when whoami failed, and the export must fail
        closed the same way rather than offer the previous cycle's wide findings."""
        dash.locator("button[data-nav='bindings']").click()
        dash.wait_for_selector("text=grant nobody")
        dash.wait_for_selector("#export-csv")
        assert dash.evaluate("() => !!(data.findings && !data.findings.forbidden)") is True
        dash.evaluate("() => { data.whoami = null; render(); }")
        assert "Loading" in dash.locator(".empty-note").first.inner_text()
        assert dash.locator("#export-csv").count() == 0
        assert dash.evaluate("() => exportDescriptor()") is None
        dash.evaluate("() => refresh()")
        dash.wait_for_selector("#export-csv")

    def test_formula_guard_covers_the_owasp_initiators(self, dash):
        """Review (Codex): LF and the full-width = + - @ are initiators in some locales' spreadsheets;
        numbers, objects and non-finite values are untouched or stringified as JavaScript does."""
        got = dash.evaluate("""() => ({
            apostrophe: csvField("'=already"),
            leadingSpace: csvField(" =SUM(1)"),
            lf: csvField("\\n=SUM(1)"),
            mathematicalMinus: csvField("\\u2212SUM(1)"),
            fullWidthEquals: csvField("\\uff1dSUM(1)"),
            fullWidthPlus: csvField("\\uff0b1"),
            fullWidthMinus: csvField("\\uff0d1"),
            fullWidthAt: csvField("\\uff20SUM(1)"),
            negativeNumber: csvField(-7),
            negativeString: csvField("-7"),
        })""")
        assert got == {
            "apostrophe": "'=already", "leadingSpace": "' =SUM(1)", "lf": "\"'\n=SUM(1)\"",
            "mathematicalMinus": "\u2212SUM(1)", "fullWidthEquals": "'\uff1dSUM(1)",
            "fullWidthPlus": "'\uff0b1", "fullWidthMinus": "'\uff0d1", "fullWidthAt": "'\uff20SUM(1)",
            "negativeNumber": "-7", "negativeString": "'-7",
        }

    def test_a_leading_space_before_a_formula_is_neutralised(self, dash):
        got = dash.evaluate("""() => toCsv(["a"], [
            { a: " =SUM(1)" },
            { a: -5 },
            { a: "'=already" },
        ])""")
        assert got == ("\ufeffa\r\n"
                       "' =SUM(1)\r\n"
                       "-5\r\n"
                       "'=already\r\n")


class TestExportVisibility:
    """A narrowed reader's export is their own rows and nothing else — by construction, because
    the file is built from the payload the server served them, but pinned anyway."""

    def test_a_narrowed_readers_users_export_is_their_own_row_and_says_self(self, page, scoped_server):
        p = _open_as(page, scoped_server, "alice")
        p.locator("button[data-nav='users']").click()
        p.wait_for_selector("tr[data-user='alice']")
        p.wait_for_selector("#export-json")
        with p.expect_download() as dl:
            p.click("#export-json")
        import json
        doc = json.load(open(dl.value.path()))
        assert doc["scope"] == "self" and doc["viewer"] == "alice"
        assert [r["user_name"] for r in doc["rows"]] == ["alice"]
        assert "_self_" in dl.value.suggested_filename
        text = open(dl.value.path()).read()
        for other in ("gatekeeper", "kubeadmin", "dave"):
            assert other not in text

    def test_a_narrowed_readers_access_export_is_their_own_path(self, page, scoped_server):
        p = _open_as(page, scoped_server, "alice")
        p.locator("button[data-nav='bindings']").click()
        p.wait_for_selector(".scope-banner")
        p.wait_for_selector("#export-csv")
        with p.expect_download() as dl:
            p.click("#export-csv")
        rows = TestExport._csv_rows(dl.value)
        assert rows[0][0] == "via_group"
        names = {r[5] for r in rows[1:]}
        assert names == {"managed-admin-rb", "hand-made-crb"}, names

    def test_narrowed_access_json_says_the_servers_order_not_a_name_sort(self, page, scoped_server):
        """Review (Cursor): the rows arrive in the store's order and the page does not re-sort
        them, so the envelope must not claim a sort it did not do."""
        p = _open_as(page, scoped_server, "alice")
        p.locator("button[data-nav='bindings']").click()
        p.wait_for_selector("#export-json")
        with p.expect_download() as dl:
            p.click("#export-json")
        import json
        doc = json.load(open(dl.value.path()))
        assert doc["sort"] == {"key": "binding_kind,binding_namespace,binding_name", "dir": "asc"}
        assert [r["binding_name"] for r in doc["rows"]] == ["hand-made-crb", "managed-admin-rb"]

    def test_narrowed_namespace_audit_json_names_the_servers_order(self, page, scoped_server):
        """Review (Codex): a narrowed reader's rows are painted as served; a sort retained from a former
        wide view must not be attributed to them."""
        p = _open_as(page, scoped_server, "carol")
        p.locator("button[data-nav='nsaudit']").click()
        p.wait_for_selector(".scope-banner")
        p.wait_for_selector("#export-json")
        p.evaluate("() => { view.nsGrantSort = 'person'; view.nsGrantDir = 'desc'; render(); }")
        with p.expect_download() as dl:
            p.click("#export-json")
        import json
        doc = json.load(open(dl.value.path()))
        assert doc["scope"] == "self"
        assert doc["sort"] == {"key": "cluster_admin_first,cluster_scope_first,binding_namespace,user_name", "dir": "asc"}
        assert [r["binding_name"] for r in doc["rows"]] == ["carol-ca"]

    def test_a_narrowed_reader_gets_the_control_back_after_the_tier_resolves(self, page, scoped_server):
        """Review pass 2 (Cursor): the restore path for a NARROWED reader — whoami nulled, no control,
        then refresh() walks the myAccess follow-up and the control returns."""
        p = _open_as(page, scoped_server, "alice")
        p.locator("button[data-nav='bindings']").click()
        p.wait_for_selector(".scope-banner")
        p.wait_for_selector("#export-csv")
        p.evaluate("() => { data.whoami = null; render(); }")
        assert p.locator("#export-csv").count() == 0
        p.evaluate("() => refresh()")
        p.wait_for_selector("#export-csv")
        assert p.evaluate("() => exportDescriptor().scope") == "self"

    def test_the_administrator_exports_the_whole_cluster(self, page, scoped_server):
        p = _open_as(page, scoped_server, "root")
        p.locator("button[data-nav='users']").click()
        p.wait_for_selector("tr[data-user='kubeadmin']")
        with p.expect_download() as dl:
            p.click("#export-json")
        import json
        doc = json.load(open(dl.value.path()))
        assert doc["scope"] == "all" and doc["count"] == 3


@pytest.fixture(scope="module")
def providers_server(tmp_path_factory):
    """The Users tab under a provider allow-list (config.users.providers = ldap-local): kubeadmin
    (developer) is not a row, the note says which providers are shown, and the never-logged-in line
    is not narrowed."""
    db = str(tmp_path_factory.mktemp("gsd-prov") / "prov.db")
    _seed(db)
    settings = Settings(
        clusters=[ClusterConfig("crc-local", "https://api.crc.testing:6443", token_env="X")],
        db_path=db,
        users_providers=("ldap-local",),
    )
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(
        build_app(settings, run_poller=False), host="127.0.0.1", port=port,
        log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(f"{base}/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        raise RuntimeError("dashboard server did not start")
    yield base
    srv.should_exit = True
    thread.join(timeout=5)


class TestIdentityFirstLogin:
    """C2: the Users tab says whether a first-login time is the Identity's creation (chip `identity`)
    or the User's (chip `approx.`), and never calls either "exact" — a lookup-mapped provider's
    Identity predates the first login (review of C2, Codex)."""

    def test_the_status_says_which_time_the_row_carries(self, dash):
        dash.locator("button[data-nav='users']").click()
        dash.wait_for_selector("tr[data-user='alice']")
        alice = dash.locator("tr[data-user='alice']")
        assert "identity" in alice.inner_text()
        assert "approx." in dash.locator("tr[data-user='kubeadmin']").inner_text()
        assert "exact" not in alice.inner_text().lower()
        assert "lookup" in alice.locator("span.chip").last.get_attribute("title"), "the chip's title states the caveat"

    def test_the_identities_note_names_the_state(self, dash):
        dash.locator("button[data-nav='users']").click()
        dash.wait_for_selector("tr[data-user='alice']")
        assert "approximate" in dash.locator("#users-identities-note").inner_text()  # off by default
        dash.evaluate("() => { data.users = Object.assign({}, data.users, { identities_source: 'forbidden' }); render(); }")
        note = dash.locator("#users-identities-note")
        assert "not permitted to list identities" in note.inner_text()
        assert "rbac.identities" in note.inner_text()
        dash.evaluate("() => { data.users = Object.assign({}, data.users, { identities_source: 'ok' }); render(); }")
        ok_note = dash.locator("#users-identities-note").inner_text()
        assert "Identity object's creation time" in ok_note and "otherwise" in ok_note, "a per-row description, not 'all exact'"
        assert "lookup" in ok_note and "exact" not in ok_note.lower()
        dash.evaluate("() => refresh()")
        dash.wait_for_function("() => data.users && data.users.identities_source === 'off'")

    def test_the_allow_list_is_said_and_applied(self, page, providers_server):
        page.goto(providers_server + "#page=users&cluster=crc-local")
        page.wait_for_selector("tr[data-user='alice']")
        assert "ldap-local" in page.locator("#users-provider-filter").inner_text()
        assert page.locator("tr[data-user='kubeadmin']").count() == 0
        assert page.locator("tr[data-user='gatekeeper']").count() == 1
        body = page.locator("body").inner_text()
        assert "kubeadmin" not in body
        assert "1 synced member" in body or "never logged in" in body


@pytest.fixture(scope="module")
def idle_server(tmp_path_factory):
    """Proxy on, idle timeout ON at 600 s with a 60 s warning, restrictions off so the seeded wide
    page renders for any name. Real seconds are never waited for: page.clock drives the model."""
    db = str(tmp_path_factory.mktemp("gsd-idle") / "ui.db")
    _seed(db)
    settings = Settings(
        clusters=[ClusterConfig("crc-local", "https://api.crc.testing:6443", token_env="X")],
        db_path=db, oauth_proxy_enabled=True, view_restrictions_enabled=False,
        session_idle_timeout_enabled=True, session_idle_timeout_seconds=600,
        session_idle_timeout_warning_seconds=60,
    )
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(
        build_app(settings, run_poller=False), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(f"{base}/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        raise RuntimeError("dashboard server did not start")
    yield base
    srv.should_exit = True
    thread.join(timeout=5)


def _open_idle(page, base):
    """A clocked page: Date.now and every timer are the test's to advance."""
    page.clock.install()
    page.set_extra_http_headers({"X-Forwarded-User": "alice"})
    page.goto(f"{base}/#page=overview")   # the idle model is the subject; the Overview is just a painted page
    page.wait_for_selector(".hero .value", timeout=10_000)
    page.wait_for_function("() => idle.enabled === true", timeout=10_000)
    return page


class TestIdleTimeout:
    """The countdown dialog and what it enforces (docs/DESIGN_session_and_signout.md)."""

    def test_the_module_off_starts_no_model(self, browser, proxied_server):
        ctx = browser.new_context(extra_http_headers={"X-Forwarded-User": "alice"})
        p = ctx.new_page()
        try:
            p.goto(proxied_server)
            p.wait_for_selector("#main .card", timeout=10_000)
            p.wait_for_function("() => sessionCapNote !== ''")
            assert p.evaluate("() => idle.enabled") is False
            assert p.locator("#idle-modal").is_hidden()
        finally:
            ctx.close()

    def test_the_dialog_opens_at_the_warning_moment_traps_focus_and_counts(self, page, idle_server):
        p = _open_idle(page, idle_server)
        p.clock.run_for(539_000)
        assert p.locator("#idle-modal").is_hidden()
        p.clock.run_for(2_000)
        assert p.locator("#idle-modal").is_visible()
        dlg = p.locator("#idle-modal [role='dialog']")
        assert dlg.get_attribute("aria-modal") == "true"
        assert dlg.get_attribute("aria-labelledby") == "idle-title"
        assert p.evaluate("() => document.activeElement.id") == "idle-stay"
        assert p.evaluate("() => document.getElementById('wrap').inert") is True
        left = int(p.locator("#idle-countdown").inner_text())
        assert 55 <= left <= 59, left
        p.clock.run_for(10_000)
        assert int(p.locator("#idle-countdown").inner_text()) == left - 10

    def test_escape_keeps_the_session_and_restores_focus(self, page, idle_server):
        p = _open_idle(page, idle_server)
        p.focus("button[data-nav='groups']")
        p.clock.run_for(545_000)
        assert p.locator("#idle-modal").is_visible()
        p.keyboard.press("Escape")
        assert p.locator("#idle-modal").is_hidden()
        assert p.evaluate("() => idle.state") == "active"
        assert p.evaluate("() => document.getElementById('wrap').inert") is False
        assert p.evaluate("() => document.activeElement.dataset.nav") == "groups"
        p.clock.run_for(300_000)
        assert p.locator("#idle-modal").is_hidden(), "the clock restarted"

    def test_enter_on_the_default_button_keeps_the_session(self, page, idle_server):
        p = _open_idle(page, idle_server)
        p.clock.run_for(545_000)
        p.keyboard.press("Enter")
        assert p.locator("#idle-modal").is_hidden()

    def test_tab_cycles_inside_the_dialog(self, page, idle_server):
        p = _open_idle(page, idle_server)
        p.clock.run_for(545_000)
        p.keyboard.press("Tab")
        assert p.evaluate("() => document.activeElement.id") == "idle-signout"
        p.keyboard.press("Tab")
        assert p.evaluate("() => document.activeElement.id") == "idle-stay"
        p.keyboard.press("Shift+Tab")
        assert p.evaluate("() => document.activeElement.id") == "idle-signout"

    def test_the_poll_is_suspended_while_the_warning_is_up_and_resumes_after_stay(self, page, idle_server):
        p = _open_idle(page, idle_server)
        p.evaluate("() => { window.__calls = 0; const f = window.fetch;"
                   " window.fetch = (...a) => { window.__calls++; return f(...a); }; }")
        p.clock.run_for(545_000)
        # The nine polls BEFORE the warning (one a minute while active) are legitimate and counted
        # above; the assertion is about the poll under the countdown, so the counter starts here.
        assert p.evaluate("() => idle.state") == "warning"
        p.evaluate("() => { window.__calls = 0; }")
        p.evaluate("() => autoRefresh()")
        assert p.evaluate("() => window.__calls") == 0, "the poll ran under the countdown"
        p.keyboard.press("Escape")
        p.wait_for_function("() => window.__calls > 0", timeout=10_000)  # the re-proof refresh
        before = p.evaluate("() => window.__calls")
        p.evaluate("() => autoRefresh()")
        p.wait_for_function(f"() => window.__calls > {before}", timeout=10_000)

    def test_expiry_blanks_the_page_and_navigates_to_the_proxys_sign_out(self, page, idle_server):
        p = _open_idle(page, idle_server)
        p.route("**/oauth/sign_out", lambda route: route.fulfill(
            status=200, content_type="text/html", body="<html><body>stub sign_out</body></html>"))
        p.clock.run_for(601_000)
        p.wait_for_url("**/oauth/sign_out", timeout=10_000)

    def test_activity_in_another_tab_defers_this_tabs_timeout(self, browser, idle_server):
        ctx = browser.new_context(extra_http_headers={"X-Forwarded-User": "alice"})
        a, b = ctx.new_page(), ctx.new_page()
        try:
            a.clock.install()
            a.goto(idle_server)
            a.wait_for_function("() => idle.enabled === true", timeout=10_000)
            b.goto(idle_server)
            b.wait_for_function("() => idle.enabled === true", timeout=10_000)
            a.clock.run_for(400_000)
            b.keyboard.press("ArrowDown")           # activity in the OTHER tab
            a.wait_for_function("() => Date.now() - idle.lastActivityAt < 1000", timeout=5_000)
            a.clock.run_for(300_000)                 # 300 s since the other tab's activity
            assert a.locator("#idle-modal").is_hidden()
            a.clock.run_for(300_000)                 # now 600 s: it fires
            assert a.locator("#idle-modal").is_visible() or "sign_out" in a.url
        finally:
            ctx.close()

    def test_nothing_is_persisted_across_a_reload(self, page, idle_server):
        """The localStorage trap: an origin recorded there outlives the session and fires early."""
        p = _open_idle(page, idle_server)
        p.clock.run_for(545_000)
        assert p.evaluate("() => localStorage.length") == 0
        p.reload()
        p.wait_for_function("() => idle.enabled === true", timeout=10_000)
        assert p.evaluate("() => idle.state") == "active"
        assert p.locator("#idle-modal").is_hidden()

    def test_sign_out_now_blanks_and_escape_cannot_revive(self, page, idle_server):
        """Review of C4 (Cursor): "Sign out now" only flipped the state, leaving the rows on screen and
        Escape able to put the reader back on a live session."""
        p = _open_idle(page, idle_server)
        p.evaluate("() => { idle.logoutUrl = null; document.getElementById('idle-signout').href = '#'; }")
        p.clock.run_for(545_000)
        assert p.locator("#idle-modal").is_visible()
        p.locator("#idle-signout").click()
        assert p.evaluate("() => idle.state") == "expired"
        assert "Signed out after inactivity" in p.locator("#main").inner_text()
        assert p.locator("#filters").inner_text() == ""
        p.keyboard.press("Escape")
        assert p.evaluate("() => idle.state") == "expired"
        assert "Signed out after inactivity" in p.locator("#main").inner_text()
        assert p.evaluate("() => document.querySelector('.hero')") is None

    def test_an_in_flight_refresh_does_not_restore_rows_or_the_ended_panel(self, page, idle_server):
        """Review of C4 (Cursor): a refresh that started while active could paint rows — or the cap's
        "session has ended" panel — over the inactivity card after expiry."""
        p = _open_idle(page, idle_server)
        p.evaluate("() => { idle.logoutUrl = null; }")
        held = []
        p.route("**/api/alerts", lambda route: held.append(route))
        # Fire and forget: evaluate() would await the promise refresh() returns, and that promise is
        # held open by the intercepted request above.
        p.evaluate("() => { refresh({auto: true}); }")
        p.clock.run_for(601_000)
        assert p.evaluate("() => idle.state") == "expired"
        assert "Signed out after inactivity" in p.locator("#main").inner_text()
        for route in held:
            route.fallback()
        p.clock.run_for(1_000)
        assert "Signed out after inactivity" in p.locator("#main").inner_text()
        assert "Your session has ended" not in p.locator("#main").inner_text()
        assert p.evaluate("() => document.querySelector('.hero')") is None

    def test_browser_back_does_not_fetch_during_the_warning(self, page, idle_server):
        """Review of C4 (Cursor): popstate called refresh() straight — Back is not inert."""
        p = _open_idle(page, idle_server)
        p.locator("button[data-nav='groups']").click()
        p.wait_for_function("() => view.page === 'groups'")
        p.clock.run_for(545_000)
        assert p.evaluate("() => idle.state") == "warning"
        p.evaluate("() => { window.__calls = 0; const f = window.fetch;"
                   " window.fetch = (...a) => { window.__calls++; return f(...a); }; }")
        p.go_back()
        p.clock.run_for(1_000)
        assert p.evaluate("() => window.__calls") == 0
        # Second pass (Cursor): Back must still APPLY the position it moved to — the first gate
        # returned before applyPosition and left the view on Groups under an Overview URL.
        assert p.evaluate("() => view.page") == "overview"
        # A hash edit reaches the hashchange handler by another path (review of C4, Codex).
        p.evaluate("() => { location.hash = '#page=users'; }")
        p.clock.run_for(1_000)
        assert p.evaluate("() => window.__calls") == 0

    def test_header_refresh_after_sign_out_now_does_not_restore_rows(self, page, idle_server):
        """Second pass (Cursor): after expiry #wrap is not inert (the "Sign in again" link must work),
        so the header's Refresh reaches refresh() — whose early return is what keeps the card."""
        p = _open_idle(page, idle_server)
        p.evaluate("() => { idle.logoutUrl = null; document.getElementById('idle-signout').href = '#'; }")
        p.clock.run_for(545_000)
        p.locator("#idle-signout").click()
        assert p.evaluate("() => idle.state") == "expired"
        p.evaluate("() => { window.__calls = 0; const f = window.fetch;"
                   " window.fetch = (...a) => { window.__calls++; return f(...a); }; }")
        p.locator("#refresh").click()
        p.clock.run_for(1_000)
        assert p.evaluate("() => window.__calls") == 0
        assert "Signed out after inactivity" in p.locator("#main").inner_text()
        assert p.evaluate("() => document.querySelector('.hero')") is None

    def test_the_skip_link_is_inert_while_the_dialog_is_open(self, page, idle_server):
        """Review of C4 (Cursor): the skip link is a sibling of #wrap, so it stayed reachable."""
        p = _open_idle(page, idle_server)
        p.clock.run_for(545_000)
        assert p.evaluate("() => document.querySelector('a.skip').inert") is True
        p.keyboard.press("Escape")
        assert p.evaluate("() => document.querySelector('a.skip').inert") is False

    def test_forced_colors_keeps_a_visible_border(self, page, idle_server):
        p = _open_idle(page, idle_server)
        p.emulate_media(forced_colors="active")
        p.clock.run_for(545_000)
        width = p.evaluate("() => getComputedStyle(document.querySelector('.idle-dialog')).borderTopWidth")
        assert width == "2px", width


# ──────────────────────────────────────────────────────────────────────────────────────────────────
# The Reports tab (docs/specs/SPEC_C3_reporting_microservice.md §9.11). The proxy's path routing is
# simulated IN-PROCESS: one uvicorn serving an ASGI router that sends /report/* to the report
# service and everything else to the dashboard, both trusting the X-Forwarded-User the browser
# context sends — the way scoped_server already simulates the proxy.
# ──────────────────────────────────────────────────────────────────────────────────────────────────

REPORT_SECRET = b"u" * 48


@pytest.fixture(scope="module")
def reporting_server(tmp_path_factory):
    from datetime import UTC as _UTC, datetime as _dt
    from gsd.reporting.config import REPORT_NAMES, ReportSettings
    from gsd.reporting.server import build_report_app
    from gsd.store import Store as _Store

    root = tmp_path_factory.mktemp("gsd-report")
    db = str(root / "ui.db")
    _seed(db)
    snapshots, artifacts, token = root / "snapshots", root / "artifacts", root / "token"
    snapshots.mkdir(); artifacts.mkdir(); token.write_bytes(REPORT_SECRET)
    writer = _Store(db)
    assert writer.snapshot(str(snapshots), keep=2)
    writer.close()
    from pathlib import Path
    vendor = Path(__file__).resolve().parents[1] / "gsd" / "static" / "vendor"
    # Live unless a test pins it. The service verifies every ticket against THIS clock while the
    # dashboard mints with wall time, so a clock frozen at creation refused every ticket minted more
    # than MAX_CLOCK_SKEW_SECONDS (30) later as future-dated — a 403, which reportFetch does not remint
    # on (401 only) — and the whole class painted the refusal card when the fixture was created ahead
    # of it (OB1, review 2 of #179). A test that needs a fixed instant sets clock["now"] and clears it.
    clock = {"now": None}
    report_settings = ReportSettings(snapshot_dir=str(snapshots), artifact_dir=str(artifacts), pdf_enabled=True, pdf_variant="pdf/a-2b",
                                     font_regular=str(vendor / "DejaVuSans.ttf"), font_bold=str(vendor / "DejaVuSans-Bold.ttf"),
                                     enabled_reports=tuple(n for n in REPORT_NAMES if n != "login-activity"),
                                     login_capture_enabled=False)
    report_app = build_report_app(report_settings, secret=REPORT_SECRET, clock=lambda: clock["now"] or _dt.now(_UTC))
    settings = Settings(
        clusters=[ClusterConfig("crc-local", "https://api.crc.testing:6443", token_env="X")],
        db_path=db, login_capture_enabled=True, oauth_proxy_enabled=True,
        reporting_url="http://127.0.0.1:1/unused", reporting_token_file=str(token), reporting_ticket_ttl_seconds=120,
    )
    dash_app = build_app(settings, run_poller=False)
    dash_app.state.tier_resolver = _TierByName()

    async def router(scope, receive, send):
        if scope["type"] == "lifespan":
            # uvicorn runs with lifespan off (below); the report worker is started by hand.
            return
        target = report_app if scope.get("path", "").startswith("/report") else dash_app
        await target(scope, receive, send)

    report_app.state.runs.start()
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(router, host="127.0.0.1", port=port, log_level="warning", lifespan="off"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(f"{base}/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        raise RuntimeError("reporting dashboard server did not start")
    yield base, clock, report_app
    srv.should_exit = True
    thread.join(timeout=5)
    report_app.state.runs.stop()


def _reports_page(browser, base, user, fake_clock=False):
    ctx = browser.new_context(extra_http_headers={"X-Forwarded-User": user, "X-Forwarded-Email": f"{user}@example.com"}, accept_downloads=True)
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    if fake_clock:
        page.clock.install()          # before navigation, so the page's own timers are the fake clock's
    page.goto(base)
    page.wait_for_selector('button.tab:text-is("Overview")', timeout=10_000)   # the nav renders for every tier
    return ctx, page, errors


class TestReportsTab:
    def test_the_fixtures_report_service_keeps_wall_time(self, reporting_server):
        """The service verifies every ticket against ITS clock while the dashboard mints with wall time; a
        fixture clock frozen at creation refused any ticket minted more than MAX_CLOCK_SKEW_SECONDS (30)
        later as "issued too far in the future" — a 403 the page cannot remint past (it remints on 401
        only), so it painted the narrowed-reader refusal card where the picker belongs. Measured: 200 at
        3 s after creation, 403 at 80 s; in CI the shell sweep created this fixture ten minutes before
        the class (OB1, review 2 of #179). The snapshot's age is the service's clock read over the wire:
        it has to move."""
        import time as _time
        from gsd.reporting.ticket import mint as _mint
        base, _clock, _app = reporting_server
        headers = {"X-Forwarded-User": "root", "X-GSD-Report-Ticket": _mint(REPORT_SECRET, "root", "all", 120)}

        def age() -> int:
            r = httpx.get(f"{base}/report/api/snapshot", headers=headers, timeout=5)
            assert r.status_code == 200, f"{r.status_code} {r.text}: a ticket minted now is refused — the service clock is behind wall time"
            return r.json()["age_seconds"]

        first = age()
        _time.sleep(1.2)
        second = age()
        assert second >= first + 1, f"the report service's clock is frozen: {first} -> {second}"

    def test_the_reports_tab_is_inside_the_viewport_too(self, browser, reporting_server):
        """The phone-width sweep runs on `server`, which has no reporting, so it sees eight tabs; the
        live bar was nine wide and Reports the first off the edge (OB1, review of #179). Measured here,
        beside the other users of the module-scoped `reporting_server`: created ten minutes ahead of
        this class (the first cut placed it in the shell sweep), the fixture's then-frozen clock refused
        every later-minted ticket as future-dated (the 30 s skew bound, a 403 the page does not remint
        on) and every test of this class timed out on `#report-picker` — in the full suite only. The
        earlier reading, "outlived its 300 s TTL", was wrong: the TTL is 120 s and the bound that bit
        was the skew (OB1, review 2 of #179); the clock is live now, and a guard test holds it so."""
        base, _clock, _app = reporting_server
        ctx, page, errors = _reports_page(browser, base, "alice")
        try:
            page.set_viewport_size({"width": 375, "height": 740})
            page.click("#tab-reports")
            page.wait_for_selector("#tab-reports[aria-current='page']")
            page.wait_for_timeout(300)
            assert page.evaluate("() => document.querySelectorAll('button.tab').length") == 11   # Home joined the strip (#158); KPIs (#157)
            assert page.evaluate("() => [document.documentElement.scrollWidth <= innerWidth, [...document.querySelectorAll('button.tab')].filter(t => t.getBoundingClientRect().right > innerWidth).map(t => t.id)]") == [True, []]
            assert not errors
        finally:
            ctx.close()

    def test_the_administrator_generates_a_report_and_downloads_the_pdf(self, browser, reporting_server):
        base, _, _ = reporting_server
        ctx, page, errors = _reports_page(browser, base, "root")
        try:
            page.click('button.tab:text-is("Reports")')
            page.wait_for_selector("#report-picker")
            entries = page.locator(".report-pick")
            assert entries.count() == 11
            login = page.locator("#report-pick-login-activity")
            assert login.is_disabled() and "reporting.reports.loginActivity.enabled" in login.inner_text()
            page.click("#report-pick-namespace-access")
            page.fill("#report-param-namespace-access-namespaces", "prod-ns")
            page.locator("#report-param-namespace-access-namespaces").dispatch_event("change")
            gen = page.locator("#report-generate")
            gen.focus()
            gen.click()
            page.wait_for_selector("#report-status:has-text('done')", timeout=30_000)
            assert page.evaluate("document.activeElement && document.activeElement.id") == "report-generate", "focus survives the repaints"
            status = page.locator("#report-status").inner_text()
            assert "sha256" in status and "data as of" in status
            buttons = page.locator("#report-status [data-artifact]")
            assert sorted(buttons.evaluate_all("els => els.map(e => e.dataset.format)")) == ["html", "json", "pdf"]
            with page.expect_download() as dl:
                page.click('#report-status [data-artifact][data-format="pdf"]')
            path = dl.value.path()
            from pathlib import Path
            assert Path(path).read_bytes().startswith(b"%PDF") and dl.value.suggested_filename.endswith(".pdf")
            page.wait_for_selector("#report-runs tbody tr")
            assert "namespace-access" in page.locator("#report-runs").inner_text() and "root" in page.locator("#report-runs").inner_text()
            assert not errors, errors
        finally:
            ctx.close()

    def test_the_multidimension_selector_posts_a_map_and_resets_on_cluster_switch(self, browser, reporting_server):
        # P2 + review #117 (C2/C4/C5): the form renders ONE multi-select PER configured dimension
        # (company.net/mnemonic AND company.net/app-environment); the id is index-based because a dotted
        # label is not a valid CSS id, and the real key is in data-selector-label. The POST carries
        # `selectors` as a {label: [values]} map (each select's `.value` gives only the first option); a
        # cluster switch drops the stale selection so cluster A's values are never posted against B.
        import json as _json
        base, _, _ = reporting_server
        ctx, page, errors = _reports_page(browser, base, "root")
        try:
            page.click('button.tab:text-is("Reports")')
            page.wait_for_selector("#report-picker")
            page.evaluate("""() => {
                data.reportCatalog.namespaceSelectorDimensions = {
                    "crc-local": [
                        {label: "company.net/mnemonic", values: ["beta", "demo"]},
                        {label: "company.net/app-environment", values: ["prod", "qa"]},
                    ],
                    "prod-east": [
                        {label: "company.net/mnemonic", values: ["gamma"]},
                        {label: "company.net/app-environment", values: ["prod"]},
                    ],
                };
                view.reportPick = "namespace-access";
                render();
            }""")
            assert page.locator('[data-param="selectors"]').count() == 2                       # one select per dimension
            assert page.locator("#report-selector-0").get_attribute("data-selector-label") == "company.net/mnemonic"
            assert page.locator("#report-selector-1").get_attribute("data-selector-label") == "company.net/app-environment"
            assert page.locator("#report-selector-0 option").evaluate_all("es => es.map(o => o.value)") == ["beta", "demo"]
            assert page.locator("#report-param-namespace-access-namespaces").count() == 1      # advanced field kept
            page.select_option("#report-selector-0", ["beta", "demo"]); page.locator("#report-selector-0").dispatch_event("change")
            page.select_option("#report-selector-1", ["prod"]); page.locator("#report-selector-1").dispatch_event("change")
            assert page.evaluate("() => view.reportForm['namespace-access'].selectors") == {
                "company.net/mnemonic": ["beta", "demo"], "company.net/app-environment": ["prod"]}
            # The actual POST carries the MAP against THIS cluster. expect_request resolves when the
            # request is SENT, so the body is captured whatever the run's own outcome.
            with page.expect_request(lambda r: r.url.endswith("/api/runs") and r.method == "POST") as info:
                page.locator("#report-generate").click()
            body = _json.loads(info.value.post_data)
            assert body["cluster"] == "crc-local"
            assert body["params"]["selectors"] == {
                "company.net/mnemonic": ["beta", "demo"], "company.net/app-environment": ["prod"]}
            # A cluster switch through the real navigate() -> applyPosition path drops the stale selection
            # and re-lists the new cluster's dimensions, so a cluster-A value can never reach cluster B.
            page.evaluate("() => { navigate({ cluster: 'prod-east', groupsync: null, group: null, user: null }); render(); }")
            assert page.evaluate("() => (view.reportForm['namespace-access'] || {}).selectors") is None
            assert page.locator("#report-selector-0 option").evaluate_all("es => es.map(o => o.value)") == ["gamma"]
            assert not errors, errors
        finally:
            ctx.close()

    def test_an_older_preview_response_cannot_overwrite_the_newer_selection(self, browser, reporting_server):
        # C4-A: clearTimeout cannot cancel a GET already sent; a late response for a superseded selection
        # must be discarded by the version token, not painted over the newer count.
        base, _, _ = reporting_server
        ctx, page, errors = _reports_page(browser, base, "root")
        try:
            page.click('button.tab:text-is("Reports")')
            page.wait_for_selector("#report-picker")
            page.evaluate("""() => {
                window.__resolvers = [];
                reportGet = () => new Promise((resolve) => { window.__resolvers.push(resolve); });
                view.cluster = "crc-local";
                view.reportForm["namespace-access"] = { selectors: {"company.net/app-environment": ["prod"]} };
                schedulePreview("namespace-access");
            }""")
            page.wait_for_function("() => window.__resolvers.length === 1")   # first GET in flight (past debounce)
            page.evaluate("""() => {
                view.reportForm["namespace-access"].selectors = {"company.net/app-environment": ["qa"]};
                schedulePreview("namespace-access");
            }""")
            page.wait_for_function("() => window.__resolvers.length === 2")
            page.evaluate("() => window.__resolvers[1]({namespaces: 2})")     # newer resolves first
            page.wait_for_function("() => view.reportPreview.startsWith('2 namespace')")
            page.evaluate("() => window.__resolvers[0]({namespaces: 1})")     # older resolves late
            page.wait_for_timeout(50)
            assert page.evaluate("() => view.reportPreview").startswith("2 namespace")   # not overwritten by 1
            assert not errors, errors
        finally:
            ctx.close()

    def test_a_proto_selector_label_is_safe(self, browser, reporting_server):
        # C4-B: a label read/assigned by own-key only, so `__proto__` never touches Object.prototype.
        base, _, _ = reporting_server
        ctx, page, errors = _reports_page(browser, base, "root")
        try:
            page.click('button.tab:text-is("Reports")')
            page.wait_for_selector("#report-picker")
            page.evaluate("""() => {
                data.reportCatalog.namespaceSelectorDimensions = {
                    "crc-local": [{label: "__proto__", values: ["prod"]}]
                };
                view.reportPick = "namespace-access";
                render();
            }""")
            page.select_option("#report-selector-0", ["prod"])
            page.locator("#report-selector-0").dispatch_event("change")
            result = page.evaluate("""() => {
                const m = view.reportForm["namespace-access"].selectors;
                return {keys: Object.keys(m), value: m["__proto__"], nullProto: Object.getPrototypeOf(m) === null};
            }""")
            assert result == {"keys": ["__proto__"], "value": ["prod"], "nullProto": True}
            assert not errors, errors
        finally:
            ctx.close()

    def test_new_frontend_falls_back_to_an_old_pods_mnemonic_control(self, browser, reporting_server):
        # C7-A: an old report pod has no `selectors` ParamSpec; the form must keep rendering the single
        # `mnemonics` control from namespaceSelectors, not hide every selector.
        base, _, _ = reporting_server
        ctx, page, errors = _reports_page(browser, base, "root")
        try:
            page.click('button.tab:text-is("Reports")')
            page.wait_for_selector("#report-picker")
            page.evaluate("""() => {
                const spec = data.reportCatalog.reports.find((r) => r.name === "namespace-access");
                spec.params = spec.params.filter((p) => p.name !== "selectors");   // old pod: no selectors spec
                delete data.reportCatalog.namespaceSelectorDimensions;
                data.reportCatalog.namespaceSelectors = {"crc-local": {label: "company.net/mnemonic", values: ["demo", "gsd"]}};
                view.reportPick = "namespace-access";
                render();
            }""")
            assert page.locator("#report-mnemonics").count() == 1
            assert page.locator("#report-mnemonics option").evaluate_all("es => es.map(o => o.value)") == ["demo", "gsd"]
            assert page.locator('[data-param="selectors"]').count() == 0
            page.select_option("#report-mnemonics", ["demo"]); page.locator("#report-mnemonics").dispatch_event("change")
            assert page.evaluate("() => view.reportForm['namespace-access'].mnemonics") == ["demo"]
            assert not errors, errors
        finally:
            ctx.close()

    def test_switching_back_to_the_report_recomputes_the_retained_preview(self, browser, reporting_server):
        # V2-F1 (2nd pass): leaving the report clears the count; returning with the selection retained
        # must recompute it, not leave it blank until the next change.
        base, _, _ = reporting_server
        ctx, page, errors = _reports_page(browser, base, "root")
        try:
            page.click('button.tab:text-is("Reports")')
            page.wait_for_selector("#report-picker")
            page.evaluate("""() => {
                reportGet = async () => ({namespaces: 2});
                data.reportCatalog.namespaceSelectorDimensions = {
                    "crc-local": [{label: "company.net/mnemonic", values: ["demo"]}]
                };
                view.reportPick = "namespace-access";
                view.reportForm["namespace-access"] = { selectors: {"company.net/mnemonic": ["demo"]} };
                render();
                schedulePreview("namespace-access");
            }""")
            page.wait_for_function("() => view.reportPreview.startsWith('2 namespace')")
            page.click("#report-pick-groups")
            assert page.evaluate("() => view.reportPreview") == ""
            page.click("#report-pick-namespace-access")
            page.wait_for_function("() => view.reportPreview.startsWith('2 namespace')")
            assert not errors, errors
        finally:
            ctx.close()

    def test_the_preview_is_blank_when_an_explicit_name_conflicts_with_selectors(self, browser, reporting_server):
        # 2nd pass (Cursor): create_run 422s selectors + explicit names together; the #107 count must not
        # keep painting for a click that will refuse.
        base, _, _ = reporting_server
        ctx, page, errors = _reports_page(browser, base, "root")
        try:
            page.click('button.tab:text-is("Reports")')
            page.wait_for_selector("#report-picker")
            page.evaluate("""() => {
                window.__resolvers = [];
                reportGet = () => new Promise((resolve) => { window.__resolvers.push(resolve); });
                view.cluster = "crc-local";
                view.reportForm["namespace-access"] = { selectors: {"company.net/mnemonic": ["demo"]} };
                schedulePreview("namespace-access");
            }""")
            page.wait_for_function("() => window.__resolvers.length === 1")
            page.evaluate("() => window.__resolvers[0]({namespaces: 4})")
            page.wait_for_function("() => view.reportPreview.startsWith('4 namespace')")
            page.evaluate("""() => {
                view.reportForm["namespace-access"].namespaces = "prod-ns";
                schedulePreview("namespace-access");
            }""")
            page.wait_for_timeout(60)
            assert page.evaluate("() => view.reportPreview") == ""
            assert page.evaluate("() => window.__resolvers.length") == 1   # no new GET fired
            assert not errors, errors
        finally:
            ctx.close()

    def test_the_view_button_lists_the_matched_names_without_resizing_the_form(self, browser, reporting_server):
        # #143: the "view namespaces" affordance appears only once names exist; showModal() renders
        # the list in the browser's top layer, so the report form's height cannot change — the whole
        # "no resize" requirement, asserted as an unchanged bounding box.
        base, _, _ = reporting_server
        ctx, page, errors = _reports_page(browser, base, "root")
        try:
            page.click('button.tab:text-is("Reports")')
            page.wait_for_selector("#report-picker")
            page.evaluate("""() => {
                reportGet = async () => ({namespaces: 3, names: ["beta-prod", "demo-prod", "demo-production"]});
                data.reportCatalog.namespaceSelectorDimensions = {
                    "crc-local": [{label: "company.net/mnemonic", values: ["beta", "demo"]}]
                };
                view.reportPick = "namespace-access";
                render();
            }""")
            btn = page.locator("#report-preview-view")
            assert btn.count() == 1 and btn.is_hidden()          # no selection yet -> no affordance
            page.select_option("#report-selector-0", ["beta", "demo"])
            page.locator("#report-selector-0").dispatch_event("change")
            page.wait_for_function("() => view.reportPreview.startsWith('3 namespace')")
            assert btn.is_visible()
            before = page.locator("#report-form").bounding_box()["height"]
            btn.click()
            page.wait_for_selector("#ns-preview[open]")
            assert page.locator("#ns-preview li").all_inner_texts() == ["beta-prod", "demo-prod", "demo-production"]
            after = page.locator("#report-form").bounding_box()["height"]
            assert after == before                               # top layer: the form did not reflow
            page.keyboard.press("Escape")                        # the native dialog's own close
            page.wait_for_function("() => !document.getElementById('ns-preview').open")
            assert page.evaluate("() => document.activeElement && document.activeElement.id") == "report-preview-view"
            assert not errors, errors
        finally:
            ctx.close()

    def test_a_selection_change_hides_the_view_affordance_until_the_fresh_reply_lands(self, browser, reporting_server):
        # #144 adversarial review C3-A: between a selection change and its reply, the names on hand
        # describe the PREVIOUS selection. A dialog opened in that window painted the superseded
        # names and the landed reply never corrected it - so the affordance must offer nothing
        # until the fresh reply lands.
        base, _, _ = reporting_server
        ctx, page, errors = _reports_page(browser, base, "root")
        try:
            page.click('button.tab:text-is("Reports")')
            page.wait_for_selector("#report-picker")
            page.evaluate("""() => {
                window._gate = null;
                let call = 0;
                reportGet = async () => {
                    call += 1;
                    if (call === 1) return {namespaces: 3, names: ["beta-prod", "demo-prod", "demo-production"]};
                    return new Promise((res) => { window._gate = () => res({namespaces: 1, names: ["beta-prod"]}); });
                };
                data.reportCatalog.namespaceSelectorDimensions = {
                    "crc-local": [{label: "company.net/mnemonic", values: ["beta", "demo"]}]
                };
                view.reportPick = "namespace-access";
                render();
            }""")
            page.select_option("#report-selector-0", ["beta", "demo"])
            page.locator("#report-selector-0").dispatch_event("change")
            page.wait_for_function("() => view.reportPreview.startsWith('3 namespace')")
            btn = page.locator("#report-preview-view")
            assert btn.is_visible()
            page.select_option("#report-selector-0", ["beta"])
            page.locator("#report-selector-0").dispatch_event("change")
            # Inside the pending window: the only names on hand are the superseded selection's.
            assert btn.is_hidden()                       # FAILS before the fix: still offers A's names
            page.wait_for_function("() => !!window._gate")
            page.evaluate("() => window._gate()")        # let the fresh reply land
            page.wait_for_function("() => view.reportPreview.startsWith('1 namespace')")
            assert btn.is_visible()                      # the affordance returns with fresh names
            assert not errors, errors
        finally:
            ctx.close()

    def test_back_to_another_tab_does_not_strand_the_open_names_dialog(self, browser, reporting_server):
        # #144 adversarial review C6-D: browser Back is not inert while a modal is up, and only the
        # cluster branch of applyPosition clears the preview. A same-cluster Back from Reports must
        # close the list, not float it over a page that carries no selection.
        base, _, _ = reporting_server
        ctx, page, errors = _reports_page(browser, base, "root")
        try:
            page.click('button.tab:text-is("Reports")')   # pushes reports over the boot tab
            page.wait_for_selector("#report-picker")
            page.evaluate("""() => {
                reportGet = async () => ({namespaces: 2, names: ["beta-prod", "demo-prod"]});
                data.reportCatalog.namespaceSelectorDimensions = {
                    "crc-local": [{label: "company.net/mnemonic", values: ["beta", "demo"]}]
                };
                view.reportPick = "namespace-access";
                render();
            }""")
            page.select_option("#report-selector-0", ["beta"])
            page.locator("#report-selector-0").dispatch_event("change")
            page.wait_for_function("() => view.reportPreview.startsWith('2 namespace')")
            page.click("#report-preview-view")
            page.wait_for_selector("#ns-preview[open]")
            page.go_back()                                # same cluster, different tab
            page.wait_for_function("() => view.page !== 'reports'")
            assert page.evaluate("() => document.getElementById('ns-preview').open") is False   # FAILS before the fix
            assert not errors, errors
        finally:
            ctx.close()

    def test_escape_after_a_poll_repaint_returns_focus_to_the_view_button(self, browser, reporting_server):
        # #144 adversarial review C4-A: showModal() memorises the opener NODE; the 60 s render()
        # replaces #main wholesale, so a close after a repaint would drop focus to <body>. The
        # onclose re-aim by ID must land it on the button the current paint carries.
        base, _, _ = reporting_server
        ctx, page, errors = _reports_page(browser, base, "root")
        try:
            page.click('button.tab:text-is("Reports")')
            page.wait_for_selector("#report-picker")
            page.evaluate("""() => {
                reportGet = async () => ({namespaces: 2, names: ["beta-prod", "demo-prod"]});
                data.reportCatalog.namespaceSelectorDimensions = {
                    "crc-local": [{label: "company.net/mnemonic", values: ["beta", "demo"]}]
                };
                view.reportPick = "namespace-access";
                render();
            }""")
            page.select_option("#report-selector-0", ["beta"])
            page.locator("#report-selector-0").dispatch_event("change")
            page.wait_for_function("() => view.reportPreview.startsWith('2 namespace')")
            page.click("#report-preview-view")
            page.wait_for_selector("#ns-preview[open]")
            page.evaluate("() => render()")               # the 60 s poll repaint, forced
            page.keyboard.press("Escape")
            page.wait_for_function("() => !document.getElementById('ns-preview').open")
            # onclose re-aims focus AFTER the native restore, so wait for it to settle rather than
            # asserting instantly (an immediate read catches the mid-close state). Before the fix
            # this never becomes true and the wait times out — the fail-before.
            page.wait_for_function("() => document.activeElement && document.activeElement.id === 'report-preview-view'")
            assert not errors, errors
        finally:
            ctx.close()

    def test_the_reports_table_categorises_and_click_brings_the_form_into_view(self, browser, reporting_server):
        # #147 reports directory: the picker is a category table (bold mono names + a coloured rail and
        # chip per category), and clicking a report snaps its form into view (the "clean way",
        # scrollIntoView) so a reader never scrolls down to the running panel.
        base, _, _ = reporting_server
        ctx, page, errors = _reports_page(browser, base, "root")
        try:
            page.click('button.tab:text-is("Reports")')
            page.wait_for_selector("#report-picker table.report-table")
            assert page.locator("#report-picker tr.report-pick").count() == 11
            bf = page.locator("#report-pick-binding-findings")
            assert "r-rbac" in (bf.get_attribute("class") or "")
            assert bf.locator(".rp-chip").inner_text().strip() == "rbac"
            assert page.locator("#report-pick-groupsync-health .rp-chip").inner_text().strip() == "health"
            assert page.locator("#report-pick-namespace-access .rp-title").inner_text().strip() != ""
            # the "clean way": clicking a report far down the list brings its form into the viewport,
            # snapped near the top — without it the form sits below the 11-row table (top well past 160).
            page.click("#report-pick-access-certification")
            page.wait_for_function("""() => {
                const f = document.getElementById('report-form');
                if (!f || view.reportPick !== 'access-certification') return false;
                const r = f.getBoundingClientRect();
                return r.bottom > 0 && r.top >= -8 && r.top < 200;
            }""")
            assert not errors, errors
        finally:
            ctx.close()

    def test_clearing_the_namespace_selector_deselects_everything(self, browser, reporting_server):
        # #147: a <select multiple> has no easy deselect. Clear drops every #report-selector-N,
        # deletes view.reportForm["namespace-access"].selectors, blanks the count, hides the
        # names affordance, and closes #ns-preview — through schedulePreview so a late GET
        # cannot paint a stale count.
        base, _, _ = reporting_server
        ctx, page, errors = _reports_page(browser, base, "root")
        try:
            page.click('button.tab:text-is("Reports")')
            page.wait_for_selector("#report-picker")
            page.evaluate("""() => {
                reportGet = async () => ({namespaces: 2, names: ["beta-prod", "demo-prod"]});
                data.reportCatalog.namespaceSelectorDimensions = {
                    "crc-local": [
                        {label: "company.net/mnemonic", values: ["beta", "demo"]},
                        {label: "company.net/app-environment", values: ["prod", "qa"]},
                    ]
                };
                view.reportPick = "namespace-access";
                render();
            }""")
            clear = page.locator("#report-preview-clear")
            view_btn = page.locator("#report-preview-view")
            assert clear.count() == 1 and clear.is_hidden()          # no selection yet
            assert view_btn.is_hidden()
            page.select_option("#report-selector-0", ["beta", "demo"])
            page.locator("#report-selector-0").dispatch_event("change")
            page.select_option("#report-selector-1", ["prod"])
            page.locator("#report-selector-1").dispatch_event("change")
            page.wait_for_function("() => !document.getElementById('report-preview-clear').hidden")
            assert page.evaluate("() => view.reportForm['namespace-access'].selectors") == {
                "company.net/mnemonic": ["beta", "demo"], "company.net/app-environment": ["prod"]}
            page.wait_for_function("() => view.reportPreview.startsWith('2 namespace')")
            assert view_btn.is_visible()

            # 1) the wired button, dialog closed: a real click deselects and hides both affordances.
            #    #ns-preview opens as a modal (showModal), so Clear sits behind its backdrop while it
            #    is open — a user clicks Clear with the dialog closed.
            clear.click()
            page.wait_for_function("() => document.getElementById('report-preview-clear').hidden")
            assert page.evaluate("""() => {
                const selects = [0, 1].map((i) => document.getElementById('report-selector-' + i));
                return {
                    empty: selects.every((s) => s && s.selectedOptions.length === 0),
                    selectors: (view.reportForm['namespace-access'] || {}).selectors,
                    preview: view.reportPreview,
                    countText: document.getElementById('report-preview').textContent,
                    clearHidden: document.getElementById('report-preview-clear').hidden,
                    viewHidden: document.getElementById('report-preview-view').hidden,
                };
            }""") == {
                "empty": True, "selectors": None, "preview": "", "countText": "",
                "clearHidden": True, "viewHidden": True,
            }

            # 2) the dialog teardown: re-select, open the modal names list, then invoke the handler
            #    (Clear cannot be clicked through the backdrop) — the selection clears and #ns-preview closes.
            page.select_option("#report-selector-0", ["beta", "demo"])
            page.locator("#report-selector-0").dispatch_event("change")
            page.select_option("#report-selector-1", ["prod"])
            page.locator("#report-selector-1").dispatch_event("change")
            page.wait_for_function("() => (view.reportPreviewNames || []).length === 2")
            view_btn.click()
            page.wait_for_selector("#ns-preview[open]")
            page.evaluate("() => clearNamespaceAccessSelectors()")
            page.wait_for_function("() => !document.getElementById('ns-preview').open")
            assert page.evaluate("() => (view.reportForm['namespace-access'] || {}).selectors") is None
            assert clear.is_hidden() and view_btn.is_hidden()
            assert not errors, errors
        finally:
            ctx.close()

    def test_a_narrowed_reader_sees_the_refusal_card_never_a_blank(self, browser, reporting_server):
        base, _, _ = reporting_server
        ctx, page, errors = _reports_page(browser, base, "alice")
        try:
            page.click('button.tab:text-is("Reports")')
            page.wait_for_selector(".refusal, .card:has-text('For administrators only')", timeout=10_000)
            body = page.locator("main").inner_text()
            assert "Reports" in body and "administrators" in body.lower()
            status = page.evaluate("fetch('/report/api/reports').then(r => r.status)")
            assert status in (401, 403)
            assert not errors, errors
        finally:
            ctx.close()

    def test_an_aged_ticket_is_reminted_transparently_once(self, browser, reporting_server):
        base, clock, _ = reporting_server
        from datetime import timedelta as _td
        ctx, page, errors = _reports_page(browser, base, "root")
        statuses: list[tuple[str, int]] = []
        page.on("response", lambda r: statuses.append((r.url, r.status)) if "/report/api/" in r.url else None)
        try:
            page.click('button.tab:text-is("Reports")')
            page.wait_for_selector("#report-picker")
            # Age the ticket the PAGE holds (the report service's clock is left alone, so a fresh
            # ticket is accepted): a well-formed ticket minted five minutes ago, which the page still
            # believes valid — exactly a tab left open past the TTL.
            from gsd.reporting.ticket import mint as _mint
            import time as _time
            stale = _mint(REPORT_SECRET, "root", "all", 120, now=_time.time() - 300)
            page.evaluate("t => { data.reportTicket = { ticket: t, expiresAt: Date.now() + 100000, prefix: '/report' }; }", stale)
            statuses.clear()
            body = page.evaluate("reportGet('/api/reports')")
            assert body["reports"] and len(body["reports"]) == 11
            codes = [s for u, s in statuses if "/report/api/reports" in u]
            assert codes == [401, 200], codes
            assert not errors, errors
        finally:
            ctx.close()

    def test_a_run_finished_elsewhere_appears_on_the_next_auto_refresh(self, browser, reporting_server):
        base, _, report_app = reporting_server
        from gsd.reporting.artifacts import Run
        ctx, page, errors = _reports_page(browser, base, "root", fake_clock=True)
        try:
            page.click('button.tab:text-is("Reports")')
            page.wait_for_selector("#report-runs")
            before = page.locator("#report-runs tbody tr").count()
            run = Run(id="20990101T000000.000000Z-ffff", report="groups", cluster="crc-local", params={}, formats=["html"],
                      generated_by="schedule:weekly", generated_by_note="unattended", schedule="weekly",
                      requested_at="2099-01-01T00:00:00Z", status="done", finished_at="2099-01-01T00:00:01Z", sha256="cd" * 32)
            report_app.state.store.create(run)
            page.clock.fast_forward(61_000)
            page.wait_for_function(f"document.querySelectorAll('#report-runs tbody tr').length > {before}", timeout=10_000)
            assert "schedule:weekly" in page.locator("#report-runs").inner_text()
            assert not errors, errors
        finally:
            ctx.close()


def test_no_reports_tab_when_the_feature_is_off(dash):
    assert dash.locator('button.tab:text-is("Reports")').count() == 0
    assert dash.evaluate("fetch('/api/report/ticket').then(r => r.status)") == 404
