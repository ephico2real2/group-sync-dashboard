"""#432's scope beyond the ping, measured: with the ping OFF, the lookup (`Poller._retrieve_pending`) and a
self-login stanza (`SelfLoginSessions.credential_for`) each present the ONE configured password as whatever
account the stanza's `ldapConnectionBootstrap` names. So "ping only the accounts whose password the Secret holds"
cannot close #432 alone: two more production paths pair another account with the one password."""
from __future__ import annotations

from gsd.config import ClusterConfig
from test_fleet_lifecycle import LeaseHost, process, sessions
from test_fleet_login import T0, login_302
from test_fleet_lookup import SA_TOKEN, sa_secret, wire  # noqa: F401
from test_walk_password_scope import presented

CHART, OTHER, PASSWORD = "chart-account", "other-account", "the-one-password"


def test_the_lookup_presents_the_one_password_as_the_stanzas_bootstrap_account(tmp_path, monkeypatch, wire):
    host = LeaseHost()
    host.rotate(PASSWORD)
    stanza = ClusterConfig("other", "https://api.other.example.com:6443", sa_token_lookup=True,
                           ldap_connection_bootstrap=OTHER)
    p = process(tmp_path, monkeypatch, host, stanza, fleet_account_username=CHART, fleet_ping_enabled=False)
    wire.answers = [login_302()]
    p._retrieve_pending()
    assert presented(wire) == [(OTHER, PASSWORD)]


def test_a_self_login_stanza_presents_the_one_password_as_its_bootstrap_account(tmp_path, monkeypatch, wire):
    host = LeaseHost()
    host.rotate(PASSWORD)
    stanza = ClusterConfig("other-self", "https://api.other.example.com:6443", user_self_login=True,
                           ldap_connection_bootstrap=OTHER)
    p = process(tmp_path, monkeypatch, host, stanza, fleet_account_username=CHART, fleet_ping_enabled=False)
    p.store.upsert_cluster("other-self", stanza.api_url, True, source="values", credential="self-login")
    s = sessions(p, [T0])
    wire.answers = [login_302()]
    assert s.credential_for(p.settings.cluster("other-self")) is not None
    assert presented(wire) == [(OTHER, PASSWORD)]
