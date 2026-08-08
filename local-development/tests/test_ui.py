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

    # Display names for SOME members only, which is the real shape: a name exists only once that
    # person has logged in. alice has one, dave does not — so every member surface renders both
    # states in the same table, and "no name" is covered by the fixture rather than only by unit
    # tests. Measured on the reference cluster: 7 of 10 members named, 3 not.
    store.replace_users("crc-local", {"alice": "Alice Cooper"}, _iso(now))

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
        dash.wait_for_selector("#f-state")

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
        dash.wait_for_selector("#f-state")
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
        dash.wait_for_selector("#f-state")
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
        dash.wait_for_selector("#f-state")
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
        dash.wait_for_selector("#f-state")
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
        dash.wait_for_selector("#f-state")
        dash.locator("tr[data-group='app-ocp-rbac-alpha-ns-admin']").click()
        dash.wait_for_selector("#back-groups")

        dash.select_option("#f-cluster", "prod-east")
        dash.wait_for_function("() => !document.querySelector('#back-groups')")
        body = dash.locator("body").inner_text()
        assert "Dashboard API error" not in body, "carried the drill-down into the new cluster"

    def test_back_restores_the_cluster_it_was_captured_with(self, dash):
        dash.locator("button[data-nav='groups']").click()
        dash.wait_for_selector("#f-state")
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
        dash.wait_for_selector("#f-state")
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
        dash.wait_for_selector("#f-state")
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
        dash.wait_for_selector("#f-state")
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
        dash.wait_for_selector("#f-state")
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
        dash.wait_for_selector("#f-group-search")

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
        dash.wait_for_selector("#f-group-search")
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
        dash.wait_for_selector("#f-group-search")

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
        dash.wait_for_selector("#f-group-search")
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


@pytest.fixture(scope="module")
def proxied_server(tmp_path_factory):
    """A dashboard behind a SIMULATED proxy: oauth_proxy_enabled on, identity and token
    supplied as browser-context headers, and the revocation's one network seam
    (kube.self_cluster_client) routed into a recording MockTransport — so the whole
    sign-out journey runs with no cluster and no real oauth-proxy.

    What this deliberately cannot cover is the proxy hop itself (the cookie-clear and the
    -logout-url redirect); that is the lab's job, per the design doc's verification plan.
    """
    from unittest import mock

    from gsd import kube

    db = str(tmp_path_factory.mktemp("gsd-proxy") / "ui.db")
    _seed(db)
    revoked: list[str] = []

    def fake_client(token, timeout):
        def handler(request):
            revoked.append(request.url.path)
            return httpx.Response(200, json={"kind": "Status"})

        return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api")

    settings = Settings(
        clusters=[ClusterConfig("crc-local", "https://api.crc.testing:6443", token_env="X")],
        db_path=db,
        oauth_proxy_enabled=True,
    )
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(
        build_app(settings, run_poller=False), host="127.0.0.1", port=port,
        log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    with mock.patch.object(kube, "self_cluster_client", fake_client):
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
        yield base, revoked
        srv.should_exit = True
        thread.join(timeout=5)


class TestSignOutAffordance:
    """The header's Sign out control, end to end short of the proxy hop itself."""

    TOKEN = "sha256~ui-test-token"

    def _page(self, browser, base):
        # The context IS the simulated proxy: these headers ride every request the page
        # makes, exactly as the sidecar would add them — including the navigation to
        # /sign-out, which is where the token must arrive.
        ctx = browser.new_context(extra_http_headers={
            "X-Forwarded-User": "alice",
            "X-Forwarded-Email": "a@x.com",
            "X-Forwarded-Access-Token": self.TOKEN,
        })
        page = ctx.new_page()
        page.goto(base)
        page.wait_for_selector(".hero .value", timeout=10_000)
        return page

    def test_the_link_is_offered_and_aims_at_the_revoking_route(self, browser, proxied_server):
        """whoami said authenticated, so the control appears — pointing at the app's own
        /sign-out, never straight at the proxy, or the revocation would be skipped."""
        base, _ = proxied_server
        page = self._page(browser, base)
        try:
            link = page.locator("#logout")
            assert link.is_visible()
            assert link.get_attribute("href") == "/sign-out"
        finally:
            page.context.close()

    def test_clicking_it_revokes_and_leaves_through_the_proxy(self, browser, proxied_server):
        """One click: the app DELETEs the oauthaccesstokens object derived from the
        forwarded token, then hands the browser to the proxy's sign_out."""
        base, revoked = proxied_server
        page = self._page(browser, base)
        try:
            page.click("#logout")
            page.wait_for_url("**/oauth/sign_out", timeout=10_000)
            assert revoked, "the click never reached the revocation seam"
            assert revoked[0].startswith("/apis/oauth.openshift.io/v1/oauthaccesstokens/sha256~")
            assert self.TOKEN.removeprefix("sha256~") not in revoked[0], (
                "the raw token must never be spent as a path segment — only its hash")
        finally:
            page.context.close()

    def test_no_link_without_a_session(self, browser, server):
        """The unproxied fixture server: whoami refuses identity there, so the control must
        stay hidden — offering to end a session that does not exist is the lie the whoami
        gate exists to stop."""
        page = browser.new_page()
        try:
            page.goto(server)
            page.wait_for_selector(".hero .value", timeout=10_000)
            assert page.locator("#logout").count() == 0 or page.locator("#logout").is_hidden()
        finally:
            page.close()


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
