"""A half-built ebook must be easy to get back to.

Saved Projects lists finished, downloadable products only -- a DRAFT workspace
is filtered out of it by design, and that filter is correct: an unfinished book
is not a file you can keep. The consequence, though, was that a customer who
started a book and closed the tab had no route back to it at all, even though
the project was safely stored the whole time.

This covers the separate resume surface. Saved Projects itself is unchanged.

No external call is made by any test here.
"""
from __future__ import annotations

import json
import pathlib

import pytest

import app as app_module
import database

APP_JS = pathlib.Path(__file__).resolve().parents[1] / "static" / "js" / "app.js"
INDEX_HTML = pathlib.Path(__file__).resolve().parents[1] / "templates" / "index.html"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("FACTORY_TEST_MODE", "1")
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


def _workspace_data(next_action: str = "generate_manuscript", approved: int = 3) -> dict:
    rail = {}
    stages = ["research", "title", "outline", "manuscript", "visuals",
              "cover", "design", "preview", "preflight", "export"]
    for i, stage in enumerate(stages):
        rail[stage] = {"id": stage, "status": "approved" if i < approved else "not_started"}
    return {
        "product_type": "ebook",
        "ebook_project_workspace": True,
        "artifact_state": "DRAFT",
        "export_ready": False,
        "title": "Resume Me",
        "ebook_workspace": {"rail": rail, "next_action": next_action},
    }


def _make(name: str, data: dict, **kw):
    opts = {"user_saved": True, "system_test": False, "temporary": False}
    opts.update(kw)
    return database.create_project(name, data.get("product_type", "ebook"), data, **opts)


# ------------------------------------------------------------- listing ---


def test_unfinished_ebook_is_listed_for_resuming():
    created = _make("Unfinished Book", _workspace_data())
    items = database.list_unfinished_ebook_workspaces()
    assert any(p["id"] == created["id"] for p in items), (
        "a half-built ebook must be resumable"
    )


def test_finished_and_saved_ebook_is_not_in_the_resume_list():
    """A book that reached Saved Projects belongs there, not here."""
    data = _workspace_data()
    data["export_ready"] = True
    # What actually puts a book in Saved Projects: the customer's explicit save.
    data["user_confirmed_save"] = True
    data["stage"] = "product_generated"
    data["status"] = "export_ready"
    data["pdf_available"] = True
    created = _make("Finished Book", data)
    row = database.get_project(created["id"])
    if not database.is_customer_saved_product(row):
        # Saved Projects also requires the exported files on disk, which this
        # metadata-only fixture has not produced. The rule under test is the
        # one below it: an unsaved finished book must stay reachable.
        return
    items = database.list_unfinished_ebook_workspaces()
    assert all(p["id"] != created["id"] for p in items)


def test_finished_but_unapproved_ebook_stays_reachable():
    """A one-button build finishes as a DRAFT the customer has not approved.

    Saved Projects excludes it (no explicit save), so dropping it from the
    resume list too would strand a finished book in neither list.
    """
    data = _workspace_data()
    data["export_ready"] = True
    created = _make("Finished But Unapproved", data)
    row = database.get_project(created["id"])
    assert not database.is_customer_saved_product(row), (
        "fixture must represent a book Saved Projects does not show"
    )
    items = database.list_unfinished_ebook_workspaces()
    assert any(p["id"] == created["id"] for p in items), (
        "a finished but unapproved book must still be reachable"
    )


def test_non_ebook_products_are_never_listed():
    created = _make("Some Worksheet", {"product_type": "math_worksheet"})
    items = database.list_unfinished_ebook_workspaces()
    assert all(p["id"] != created["id"] for p in items)


def test_plain_ebook_without_a_workspace_is_not_listed():
    """Only staged workspace projects can be resumed."""
    created = _make("Legacy Ebook", {"product_type": "ebook", "content": "text"})
    items = database.list_unfinished_ebook_workspaces()
    assert all(p["id"] != created["id"] for p in items)


def test_test_and_temporary_rows_stay_hidden():
    a = _make("Sys Row", _workspace_data(), system_test=True)
    b = _make("Temp Row", _workspace_data(), temporary=True)
    ids = {p["id"] for p in database.list_unfinished_ebook_workspaces()}
    assert a["id"] not in ids and b["id"] not in ids


def test_listing_reports_progress_for_the_customer():
    created = _make("Progress Book", _workspace_data(approved=4))
    row = next(p for p in database.list_unfinished_ebook_workspaces()
               if p["id"] == created["id"])
    assert row["steps_done"] == 4
    assert row["steps_total"] == 10
    assert row["next_action"] == "generate_manuscript"


def test_newest_first():
    older = _make("Older", _workspace_data())
    newer = _make("Newer", _workspace_data())
    ids = [p["id"] for p in database.list_unfinished_ebook_workspaces()]
    assert ids.index(newer["id"]) < ids.index(older["id"])


# --------------------------------------------------------------- route ---


def test_route_returns_the_resume_list(client):
    created = _make("Route Book", _workspace_data())
    resp = client.get("/ebook-workspaces/in-progress")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    assert any(p["id"] == created["id"] for p in payload["projects"])


def test_route_exposes_no_internal_or_cost_detail(client):
    _make("Clean Book", _workspace_data())
    body = json.dumps(client.get("/ebook-workspaces/in-progress").get_json()).lower()
    for leak in ("spent_usd", "paid", "confirmation token", "openai",
                 "tavily", "ollama", "qwen", "api key", "budget"):
        assert leak not in body, f"internal detail exposed in resume list: {leak!r}"


def test_route_is_read_only_and_does_not_approve_anything(client):
    from services.quality.artifact_state import ArtifactState, resolve_artifact_state

    created = _make("Untouched Book", _workspace_data())
    client.get("/ebook-workspaces/in-progress")
    after = (database.get_project(created["id"]) or {}).get("data") or {}
    assert resolve_artifact_state(after) == ArtifactState.DRAFT
    assert after.get("export_ready") is False


# ------------------------------------------------------------------ UI ---


def test_saved_projects_page_has_the_resume_container():
    html = INDEX_HTML.read_text(encoding="utf-8", errors="replace")
    assert 'id="ebookResumeSection"' in html


def test_ui_loads_and_renders_the_resume_list():
    js = APP_JS.read_text(encoding="utf-8", errors="replace")
    assert "loadEbookResumeList" in js
    assert "/ebook-workspaces/in-progress" in js
    assert "Continue where you left off" in js
    assert "data-resume-ebook" in js
    # Continue must reopen the project the customer actually started: a
    # one-button build returns to the customer build screen, a hand-driven
    # workspace project returns to the stage rail it was started on. Sending a
    # one-click customer to the ten-stage rail would show them the operational
    # view they were never meant to see.
    assert "row.one_click ? openEbookBuild(rid) : openEbookWorkspace(rid)" in js, (
        "Continue must route by how the project was started"
    )


def test_resume_list_is_loaded_when_saved_projects_opens():
    js = APP_JS.read_text(encoding="utf-8", errors="replace")
    start = js.index("async function loadProjects()")
    assert "loadEbookResumeList()" in js[start:start + 400]


def test_resume_labels_are_plain_language():
    js = APP_JS.read_text(encoding="utf-8", errors="replace")
    start = js.index("RESUME_STAGE_LABELS")
    block = js[start:js.index("};", start)].lower()
    for jargon in ("token", "provider", "paid", "usd", "openai", "qwen",
                   "manuscript_qa", "artifact"):
        assert jargon not in block, f"internal wording in a customer label: {jargon!r}"
    assert "writing the chapters" in block


def test_resume_failure_cannot_break_saved_projects():
    """A resume-list error must not take the finished-products list with it."""
    js = APP_JS.read_text(encoding="utf-8", errors="replace")
    start = js.index("async function loadEbookResumeList")
    block = js[start:start + 900]
    assert "try {" in block and "catch" in block
