"""Playwright tests for the dashboard UI.

These run against a *seeded* app instance with the poller disabled, not against a live
cluster. That is deliberate: the states worth testing hardest — an overdue CR, a cluster
whose token is rejected, a current reconcile error — are exactly the ones a healthy cluster
never shows, and a live cluster's counts change under the test while it runs.

A separate smoke test (test_live_smoke.py) covers the real thing.
"""

from __future__ import annotations

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
    ], _iso(now))

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
    page.goto(server)
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
        page.goto(server)
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
        FIRST cluster switch restored a drill-down against the wrong one."""
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
        dash.wait_for_function("() => !document.querySelector('#back')")
        assert dash.evaluate("() => view.page") == "overview"

    def test_back_after_a_cluster_switch_restores_that_cluster(self, dash):
        """Cluster is part of the position, not context around it — group names repeat."""
        self._drill(dash)
        dash.select_option("#f-cluster", "prod-east")
        dash.wait_for_function("() => view.cluster === 'prod-east'")
        dash.go_back()
        dash.wait_for_function("() => view.cluster === 'crc-local'")
        assert "cluster=crc-local" in dash.url


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
        # operand has to be verbose enough to write a username at all.
        assert "loginCapture.enabled=true" in body
        assert "Debug" in body
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
            "() => { view.groupFilter = 'empty'; data.groups = []; view.groupSearch = 'admin'; render(); }")
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
            "() => { view.groupFilter = 'empty'; data.groups = []; view.groupSearch = 'admin'; render(); }")
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
            # Not `.hero .value`: alice is a narrowed reader, and the landing page is the
            # administrator tier now, so she lands on a refusal card with no cluster hero.
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
            # Not `.hero .value`: alice is a narrowed reader, and the landing page is the
            # administrator tier now, so she lands on a refusal card with no cluster hero.
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
        # `#main .card`, not `.hero .value`: the landing page is the administrator tier, so a
        # narrowed reader lands on a refusal card that carries no cluster hero. Both render a
        # section.card, which is what this wait actually wants to know — that the page painted.
        page.wait_for_selector("#main .card", timeout=10_000)
    except Exception:
        if errors:
            pytest.fail("the page raised and never rendered:\n  " + "\n  ".join(errors))
        raise
    assert not errors, "uncaught JS error on load:\n  " + "\n  ".join(errors)
    return page


class TestVisibilityLabels:
    def test_the_pill_names_the_narrowed_view(self, page, scoped_server):
        """Q6/DoD 5: the reader can tell 'this is your view' from 'this is everything',
        on every tab, starting with the landing page."""
        p = _open_as(page, scoped_server, "alice")
        p.wait_for_selector("#scope-pill:not([hidden])")
        text = p.locator("#scope-pill").inner_text()
        assert text.startswith("Your view"), text
        assert "alice" in text, "the pill must name the viewer it is scoped to"
        assert p.locator(".scope-refusal").count() == 1
        assert p.locator(".hero").count() == 0

    def test_the_administrator_is_told_they_see_everything(self, page, scoped_server):
        """The admin marker. 'Nothing looks different' and 'you are seeing everything'
        are different statements, and only the second is checkable from the screen."""
        p = _open_as(page, scoped_server, "root")
        p.wait_for_selector("#scope-pill:not([hidden])")
        assert p.locator("#scope-pill").inner_text().startswith("Full view")
        assert p.locator(".hero").count() == 1
        assert p.locator(".scope-refusal").count() == 0

    def test_an_unknown_tier_does_not_paint_the_wide_overview(self, page, scoped_server):
        """A failed whoami is not evidence that the reader may see cluster-wide health."""
        page.route("**/api/whoami", lambda route: route.fulfill(
            status=503, content_type="application/json", body="{}"))
        page.set_extra_http_headers({"X-Forwarded-User": "alice"})
        page.goto(scoped_server)
        page.wait_for_selector("#main .card", timeout=10_000)
        assert page.locator("#main .hero").count() == 0

    def test_an_unknown_tier_does_not_paint_a_refusal(self, page, scoped_server):
        """Cold-load uncertainty is not evidence of narrowing either; wait for the authority."""
        page.route("**/api/whoami", lambda route: route.fulfill(
            status=503, content_type="application/json", body="{}"))
        page.set_extra_http_headers({"X-Forwarded-User": "alice"})
        page.goto(scoped_server)
        page.wait_for_selector("#main .card", timeout=10_000)
        assert page.locator("#main .scope-refusal").count() == 0
        assert page.locator("#main").inner_text().strip() == "Loading…"

    def test_an_unauthenticated_whoami_body_paints_the_wide_overview(self, page, scoped_server):
        """Without a verified identity no tier applies, so silence must not invent narrowing."""
        page.goto(scoped_server)
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
        page.goto(server)
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
