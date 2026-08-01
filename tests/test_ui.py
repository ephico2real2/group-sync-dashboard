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
import pytest
import uvicorn

from gsd.api import build_app
from gsd.config import ClusterConfig, Settings
from gsd.store import Store


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


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
                "provider_key": "ldap-groupsync_ldap",
            },
            {
                # Hours past two hourly intervals -> overdue.
                "name": "bda-rbac-groupsync",
                "namespace": "group-sync-operator",
                "schedule": "0 * * * *",
                "ldap_filter": "(&(objectClass=groupOfNames)(cn=bda-rbac-*))",
                "last_sync_at": _iso(now - timedelta(hours=6)),
                "generation": 2,
                "provider_key": "bda-rbac-groupsync_ldap",
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
    page.goto(server)
    page.wait_for_selector(".hero .value")
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
        assert dash.locator("tbody tr").count() == 3

    def test_empty_filter_excludes_the_unmanaged_group(self, dash):
        """EMPTY is 'synced, zero members' — a hand-made empty group is UNATTRIBUTED."""
        self._open_groups(dash)
        dash.select_option("#f-state", "empty")
        dash.wait_for_function("document.querySelectorAll('tbody tr').length === 1")
        text = dash.locator("tbody").inner_text()
        assert "app-ocp-rbac-abcd-ns-superuser" in text
        assert "gsd-test-unattributed" not in text

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
        """Hue is the fast channel, never the only one."""
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
        assert dash.locator("tbody tr").count() == 3

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
