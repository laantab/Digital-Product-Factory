"""Bounded one-button build lookup must not deserialize unrelated saved books.

All fixtures use a temporary SQLite database. No AI providers or customer files.
"""
import sqlite3

import database
from services import ebook_build_orchestrator as orch


def _temporary_db(monkeypatch, tmp_path):
    monkeypatch.setenv("FACTORY_DB_BACKEND", "sqlite")
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "factory.sqlite3"))
    database.init_db()


def test_repeat_click_only_decodes_matching_saved_book(monkeypatch, tmp_path):
    _temporary_db(monkeypatch, tmp_path)
    key = orch.idempotency_key_for({"topic": "Winter garden"})
    unrelated = database.create_project(
        "A Springtime Recipe Collection", "ebook",
        {"content": "A" * 2_000_000, "ebook_build": {"idempotency_key": "other-key"}},
        user_saved=True, system_test=False, temporary=False,
    )
    existing = database.create_project(
        "A Cozy Winter Garden Guide", "ebook",
        {"ebook_build": {"idempotency_key": key}, "content": "Preserved manuscript"},
        user_saved=True, system_test=False, temporary=False,
    )
    decoded = []
    original_decode = database._decode_project_data

    def track_decode(raw):
        if len(raw) > 1_000_000:
            raise AssertionError("unrelated multi-megabyte ebook was decoded")
        decoded.append(len(raw))
        return original_decode(raw)

    monkeypatch.setattr(database, "_decode_project_data", track_decode)
    monkeypatch.setattr(database, "list_projects", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("full saved-project listing is forbidden for idempotency")))
    found = orch.find_existing_build(key)
    assert found["id"] == existing["id"]
    assert found["data"]["content"] == "Preserved manuscript"
    assert len(decoded) == 1
    assert unrelated["id"] != found["id"]


def test_false_hits_and_hidden_books_do_not_attach(monkeypatch, tmp_path):
    _temporary_db(monkeypatch, tmp_path)
    key = orch.idempotency_key_for({"topic": "Holiday budgeting"})
    database.create_project(
        "A Holiday Notebook", "ebook",
        {"content": "Referenced key: " + key}, user_saved=True,
        system_test=False, temporary=False,
    )
    database.create_project(
        "An Internal Holiday Guide", "ebook",
        {"ebook_build": {"idempotency_key": key}, "hidden_from_customer": True},
        user_saved=True, system_test=False, temporary=False,
    )
    assert orch.find_existing_build(key) is None
    visible = database.create_project(
        "A Simple Holiday Budget Guide", "ebook",
        {"ebook_build": {"idempotency_key": key}, "content": "Keep this"},
        user_saved=True, system_test=False, temporary=False,
    )
    assert orch.find_existing_build(key)["id"] == visible["id"]
    assert orch.find_existing_build("unseen-" + key) is None


def test_lookup_is_read_only_and_keeps_project_version(monkeypatch, tmp_path):
    _temporary_db(monkeypatch, tmp_path)
    key = orch.idempotency_key_for({"topic": "Seasonal home organization"})
    original = database.create_project(
        "Organize Your Home for Winter", "ebook",
        {"ebook_build": {"idempotency_key": key}, "preview_html": "<p>Saved</p>"},
        user_saved=True, system_test=False, temporary=False,
    )
    with sqlite3.connect(database.DB_PATH) as conn:
        before = conn.execute("SELECT data, version FROM projects WHERE id=?", (original["id"],)).fetchone()
    found = orch.find_existing_build(key)
    assert found["id"] == original["id"]
    with sqlite3.connect(database.DB_PATH) as conn:
        after = conn.execute("SELECT data, version FROM projects WHERE id=?", (original["id"],)).fetchone()
    assert before == after
    assert found["data"]["preview_html"] == "<p>Saved</p>"
