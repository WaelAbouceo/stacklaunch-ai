"""Tests for project + conversation-memory persistence (appstore.py)."""

import pytest

from data import appstore


@pytest.fixture()
def store(tmp_path):
    appstore.configure(str(tmp_path / "app.db"))
    yield appstore
    appstore.configure(appstore.config.APP_DB_PATH)


def test_save_and_get_project(store):
    project = {"id": "proj-1", "companyName": "Acme", "industry": "banking",
               "websiteUrl": "https://acme.com", "connectors": {}}
    store.save_project(project)
    got = store.get_project("proj-1")
    assert got["companyName"] == "Acme"
    assert store.list_projects()[0]["id"] == "proj-1"


def test_memory_roundtrip_in_order(store):
    store.add_turn("s1", "user", "hello", "proj-1")
    store.add_turn("s1", "assistant", "hi there", "proj-1")
    turns = store.get_turns("s1")
    assert [t["role"] for t in turns] == ["user", "assistant"]
    assert turns[0]["content"] == "hello"


def test_erasure_removes_project_and_memory(store):
    store.save_project({"id": "proj-9", "companyName": "Z", "connectors": {}})
    store.add_turn("s9", "user", "q", "proj-9")
    res = store.delete_project("proj-9")
    assert res["projectsDeleted"] == 1
    assert res["memoryRowsDeleted"] == 1
    assert store.get_project("proj-9") is None


def test_clear_session(store):
    store.add_turn("s2", "user", "a")
    store.add_turn("s2", "user", "b")
    assert store.clear_session("s2") == 2
    assert store.get_turns("s2") == []
