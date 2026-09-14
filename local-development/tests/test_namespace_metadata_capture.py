"""Extension B1 — the poll captures a bounded set of namespace labels and the store persists them
(docs/DESIGN_reporting_auditors_and_ns_selector.md §3.3, §3.4). No report/GUI change yet."""
from __future__ import annotations

import sqlite3

import pytest

from gsd.config import ClusterConfig, _string_list_setting
from gsd.kube import ClusterClient
from gsd.store import Store


NS_ITEMS = [
    {"metadata": {"name": "beta-prod", "creationTimestamp": "2026-01-01T00:00:00Z",
                  "labels": {"company.net/mnemonic": "beta", "company.net/app-environment": "prod",
                             "kubernetes.io/metadata.name": "beta-prod"}},
     "status": {"phase": "Active"}},
    {"metadata": {"name": "no-labels"}, "status": {"phase": "Active"}},
    {"metadata": {"name": ""}, "status": {"phase": "Active"}},   # nameless: skipped
]


def _client(monkeypatch, items):
    c = ClusterClient(ClusterConfig(name="crc", api_url="https://k8s"), timeout=1.0)
    monkeypatch.setattr(c, "_client", lambda: _NullCtx())
    monkeypatch.setattr(c, "_list_all", lambda client, path: items)
    return c


class _NullCtx:
    def __enter__(self): return object()
    def __exit__(self, *a): return False


class TestFetchNamespacesCapturesConfiguredKeys:
    def test_only_configured_keys_that_are_present_are_captured(self, monkeypatch):
        c = _client(monkeypatch, NS_ITEMS)
        rows = c.fetch_namespaces(["company.net/mnemonic"])
        assert [r["name"] for r in rows] == ["beta-prod", "no-labels"]   # nameless skipped
        assert rows[0]["metadata"] == {"company.net/mnemonic": "beta"}    # ONLY the configured key
        assert rows[1]["metadata"] == {}                                  # a namespace without it
        assert rows[0]["phase"] == "Active" and rows[0]["created_at"] == "2026-01-01T00:00:00Z"

    def test_two_configured_keys_stay_distinct(self, monkeypatch):
        c = _client(monkeypatch, NS_ITEMS)
        rows = c.fetch_namespaces(["company.net/mnemonic", "company.net/app-environment"])
        assert rows[0]["metadata"] == {"company.net/mnemonic": "beta", "company.net/app-environment": "prod"}

    def test_no_keys_captures_nothing(self, monkeypatch):
        c = _client(monkeypatch, NS_ITEMS)
        rows = c.fetch_namespaces([])
        assert all(r["metadata"] == {} for r in rows)
        rows_none = c.fetch_namespaces(None)                              # default: no capture
        assert all(r["metadata"] == {} for r in rows_none)

    def test_an_unconfigured_label_is_never_captured(self, monkeypatch):
        c = _client(monkeypatch, NS_ITEMS)
        rows = c.fetch_namespaces(["company.net/mnemonic"])
        assert "kubernetes.io/metadata.name" not in rows[0]["metadata"]   # bounded to the configured set


class TestStorePersistsNamespaceMetadata:
    @pytest.fixture
    def store(self):
        return Store(":memory:")

    def _labels(self, store, cluster="crc"):
        return sorted((r[0], r[1], r[2]) for r in store._conn.execute(
            "SELECT name, key, value FROM cluster_namespace_label WHERE cluster_id=?", (cluster,)))

    def test_metadata_lands_in_the_child_table(self, store):
        store.replace_namespaces("crc", [
            {"name": "beta-prod", "created_at": None, "phase": "Active",
             "metadata": {"company.net/mnemonic": "beta"}},
            {"name": "plain", "created_at": None, "phase": "Active", "metadata": {}},
        ], "2026-09-14T00:00:00Z")
        assert self._labels(store) == [("beta-prod", "company.net/mnemonic", "beta")]
        # the namespace row itself is stored regardless
        names = {r[0] for r in store._conn.execute("SELECT name FROM cluster_namespace WHERE cluster_id='crc'")}
        assert names == {"beta-prod", "plain"}

    def test_empty_value_is_skipped(self, store):
        store.replace_namespaces("crc", [
            {"name": "x", "metadata": {"company.net/mnemonic": "", "company.net/env": None}}],
            "t")
        assert self._labels(store) == []

    def test_replace_removes_stale_metadata(self, store):
        store.replace_namespaces("crc", [{"name": "a", "metadata": {"k": "1"}}], "t1")
        store.replace_namespaces("crc", [{"name": "b", "metadata": {"k": "2"}}], "t2")
        assert self._labels(store) == [("b", "k", "2")]           # a's label gone with a

    def test_a_second_cluster_is_isolated(self, store):
        store.replace_namespaces("crc", [{"name": "a", "metadata": {"k": "1"}}], "t")
        store.replace_namespaces("east", [{"name": "a", "metadata": {"k": "2"}}], "t")
        assert self._labels(store, "crc") == [("a", "k", "1")]
        assert self._labels(store, "east") == [("a", "k", "2")]

    def test_no_metadata_key_is_safe(self, store):
        store.replace_namespaces("crc", [{"name": "a", "created_at": None, "phase": "Active"}], "t")
        assert self._labels(store) == []


class TestConfigLoadsTheLabels:
    def test_from_a_list(self):
        assert _string_list_setting({"namespaceMetadataLabels": ["company.net/mnemonic"]},
                                    "namespaceMetadataLabels", ()) == ("company.net/mnemonic",)

    def test_missing_is_the_default_empty(self):
        assert _string_list_setting({}, "namespaceMetadataLabels", ()) == ()
