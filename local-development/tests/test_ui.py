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
        assert dash.locator("tbody tr").count() == 3

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
        assert dash.locator("tbody tr").count() == 3

    def test_nav_button_clears_the_trail(self, dash):
        """Jumping to a section is a fresh start, not a continuation of the old path."""
        self._open_group(dash, "app-ocp-rbac-alpha-ns-admin")
        dash.locator("tr[data-user='alice']").click()
        dash.wait_for_selector("text=Group memberships")
        dash.locator("button[data-nav='groups']").click()
        dash.wait_for_function("() => !document.querySelector('#back-groups')")
        assert dash.locator("tbody tr").count() == 3

    def test_error_page_still_offers_a_way_back(self, dash):
        """The reported dead end: a 404 replaced the page, back button included."""
        self._open_group(dash, "app-ocp-rbac-alpha-ns-admin")
        dash.evaluate("""() => {
            pushTrail();                       // what a real click does
            view.group = 'definitely-not-a-real-group-xyz';
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
            pushTrail();
            view.group = 'app-ocp-rbac-gone-ns-viewer';
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
            pushTrail();
            view.group = 'app-ocp-rbac-gone-ns-viewer';
            refresh();
        }""")
        dash.wait_for_selector("#back-groups")
        dash.locator("#back-groups").click()
        dash.wait_for_function("() => !document.querySelector('#back-groups')")
        assert dash.locator("tbody tr").count() == 3


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

        assert dash.evaluate("() => trail[trail.length - 1].cluster") == "crc-local"
        dash.locator("#back-groups").click()
        dash.wait_for_selector("text=Membership changes")
        assert dash.evaluate("() => view.cluster") == "crc-local"


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
