"""Group-detail owner resolution, against a seeded store with the poller disabled.

The rest of the API is exercised through the UI tests. This covers the one path where a
group is matched back to the CR that produced it, because that match is what a
multi-provider CR used to get wrong: only the CR's first provider key was recorded, so a
group belonging to any later provider resolved to no owner at all.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.config import ClusterConfig, Settings
from gsd.store import Store

OBSERVED = "2026-08-01T07:00:30Z"


@pytest.fixture()
def client(tmp_path):
    db = str(tmp_path / "gsd.db")
    store = Store(db)
    store.upsert_cluster("crc", "https://api.crc.testing:6443", True)
    store.replace_groupsync_state(
        "crc",
        [{"name": "corp", "namespace": "ns", "schedule": "0 * * * *", "ldap_filter": None,
          "last_sync_at": "2026-08-01T07:00:10Z", "generation": 1,
          "provider_keys": ["corp_ldap-a", "corp_ldap-b"]}],
        OBSERVED,
    )
    store.replace_group_state(
        "crc",
        [
            {"name": "from-a", "member_count": 1, "sync_provider": "corp_ldap-a",
             "group_synced_at": OBSERVED, "ldap_uid": None},
            {"name": "from-b", "member_count": 1, "sync_provider": "corp_ldap-b",
             "group_synced_at": OBSERVED, "ldap_uid": None},
            {"name": "handmade", "member_count": 1, "sync_provider": None,
             "group_synced_at": None, "ldap_uid": None},
        ],
        OBSERVED,
    )
    store.close()
    # The cluster must be in Settings as well as the store: the API validates the path
    # segment against configuration, so a cluster that only exists in the database 404s.
    settings = Settings(
        clusters=[ClusterConfig(name="crc", api_url="https://api.crc.testing:6443")],
        db_path=db,
    )
    with TestClient(build_app(settings, run_poller=False)) as c:
        yield c


def _owner(client, group):
    return client.get(f"/api/clusters/crc/groups/{group}").json()["owner"]


class TestGroupOwner:
    def test_first_provider_resolves(self, client):
        assert _owner(client, "from-a")["name"] == "corp"

    def test_later_provider_resolves_too(self, client):
        """The regression: this group carries a valid label owned by a real CR, and used to
        report `owner: null` — indistinguishable in the UI from a group nobody manages."""
        assert _owner(client, "from-b")["name"] == "corp"

    def test_unlabelled_group_still_has_no_owner(self, client):
        """The fix must not turn 'genuinely unmanaged' into a false attribution."""
        assert _owner(client, "handmade") is None
