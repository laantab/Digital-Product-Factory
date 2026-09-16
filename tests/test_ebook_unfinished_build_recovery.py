"""The live 5-of-9 ebook stall — finding a stranded build again.

THE FAILURE THIS REPRODUCES
---------------------------
A live customer's ebook stopped at "Writing your chapters (5 of 9)", 30%,
and could not be reached from any screen.

The chain, each link verified in the code:

  1. The build is driven entirely by a browser loop
     (`_ebookBuildLoop` -> POST /advance, one bounded unit per call since
     v1.7.10). There is NO server-side executor.
  2. Closing the tab stops the loop. Chapters 1-5 stay safely persisted;
     chapter 6 is simply never requested.
  3. The browser remembered the build in `sessionStorage`, which the
     browser destroys when the tab closes -- so no auto-resume.
  4. A half-built ebook has no PDF, so
     `database._has_usable_customer_output()` is False and it never
     appears in Saved Projects.

Links 3 and 4 together mean there is no route back at all. These tests
hold the fix for that: the SERVER remembers unfinished builds, so the
book can always be found and resumed.

This does not make a build survive a closed tab -- only a background
worker (0B-5) can do that. It makes a stranded build findable.
"""
from __future__ import annotations

import json

import pytest

import database
from services.ebook_build_orchestrator import (
    STAGES,
    build_is_unfinished,
    unfinished_builds,
)


def _build_data(*, chapters_done=5, chapters_total=9, finished=False, failed=False,
                stage="manuscript"):
    """A project shaped like the live stall: manuscript part-written."""
    stages = {}
    for name in STAGES:
        if name in ("research", "title", "outline"):
            stages[name] = {"status": "VALIDATED", "attempts": 1}
        elif name == stage:
            stages[name] = {"status": "IN_PROGRESS", "attempts": chapters_done}
    return {
        "product_type": "ebook",
        "title": "Container Gardening for Beginners",
        "chapters": [{"title": f"Chapter {i}", "content": "x" * 50}
                     for i in range(1, chapters_done + 1)],
        "chapter_count": chapters_total,
        "ebook_build": {
            "build_id": "bld-1",
            "started_at": "2026-09-15T10:00:00",
            "updated_at": "2026-09-15T10:30:00",
            "current_stage": stage,
            "stages": stages,
            "customer_message": f"Writing chapters ({chapters_done}/{chapters_total})",
            "finished": finished,
            "failed": failed,
        },
    }


# ======================================= recognising an unfinished build ===


def test_a_part_written_manuscript_is_unfinished():
    assert build_is_unfinished(_build_data(chapters_done=5)) is True


def test_a_finished_build_is_not_unfinished():
    assert build_is_unfinished(_build_data(finished=True)) is False


def test_a_failed_build_is_not_offered_as_resumable():
    """A failed build needs Resume Build, which is a different action."""
    assert build_is_unfinished(_build_data(failed=True)) is False


def test_a_project_that_never_started_a_build_is_not_unfinished():
    assert build_is_unfinished({"product_type": "ebook"}) is False
    assert build_is_unfinished({}) is False
    assert build_is_unfinished({"ebook_build": {}}) is False


def test_non_dict_data_never_raises():
    for value in (None, "", [], 0):
        assert build_is_unfinished(value) is False


# ========================= the stranded build is findable again ============


def test_the_stranded_build_is_returned_by_the_server(monkeypatch):
    """The whole point: the server remembers, not sessionStorage."""
    created = database.create_project(
        "Container Gardening for Beginners", "ebook", _build_data(chapters_done=5))

    builds = unfinished_builds()
    match = [b for b in builds if b["project_id"] == created["id"]]
    assert match, "a stranded build must be findable without the browser's memory"
    entry = match[0]
    assert entry["name"] == "Container Gardening for Beginners"
    assert entry["current_stage"] == "manuscript"
    assert "5/9" in entry["message"] or "5" in entry["message"]


def test_a_finished_build_is_not_offered_for_resume():
    created = database.create_project(
        "Finished Book", "ebook", _build_data(finished=True))
    assert all(b["project_id"] != created["id"] for b in unfinished_builds())


def test_system_and_temporary_records_are_never_offered():
    hidden = database.create_project(
        "[TEST] Internal", "ebook", {**_build_data(), "system_test": True})
    temp = database.create_project(
        "Temp", "ebook", {**_build_data(), "temporary": True})
    ids = {b["project_id"] for b in unfinished_builds()}
    assert hidden["id"] not in ids
    assert temp["id"] not in ids


def test_unfinished_builds_reports_paused_not_working():
    """Nothing runs server-side between requests.

    Reporting an unwatched build as 'working' is the animated-spinner-
    forever defect the customer actually saw.
    """
    database.create_project("Paused Book", "ebook", _build_data())
    for entry in unfinished_builds():
        assert entry["paused"] is True


def test_discovery_is_read_only(monkeypatch):
    created = database.create_project("Read Only", "ebook", _build_data())
    before = database.get_project(created["id"])

    unfinished_builds()

    after = database.get_project(created["id"])
    assert after["data"] == before["data"], "discovery must not mutate the project"
    assert after["data"]["_row_version"] == before["data"]["_row_version"]


def test_completed_chapters_are_never_discarded_by_discovery():
    created = database.create_project("Keep Chapters", "ebook", _build_data(chapters_done=5))
    unfinished_builds()
    stored = database.get_project(created["id"])["data"]
    assert len(stored["chapters"]) == 5, "already-written chapters must survive"


def test_the_newest_build_is_offered_first():
    old = _build_data()
    old["ebook_build"]["updated_at"] = "2026-09-01T00:00:00"
    new = _build_data()
    new["ebook_build"]["updated_at"] = "2026-09-15T23:59:00"
    database.create_project("Older", "ebook", old)
    newest = database.create_project("Newer", "ebook", new)

    builds = unfinished_builds()
    assert builds and builds[0]["project_id"] == newest["id"]


# ================================================ the route the UI calls ===


def test_the_route_returns_the_stranded_build():
    import app as app_module

    created = database.create_project(
        "Route Container Gardening", "ebook", _build_data(chapters_done=5))
    client = app_module.app.test_client()

    response = client.get("/ebook-workspaces/in-progress")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert any(b["id"] == created["id"] for b in payload["projects"])


def test_the_route_is_read_only_and_starts_nothing():
    import app as app_module

    created = database.create_project("No Side Effects", "ebook", _build_data())
    before = database.get_project(created["id"])

    app_module.app.test_client().get("/ebook-workspaces/in-progress")

    after = database.get_project(created["id"])
    assert after["data"] == before["data"]


def test_the_route_still_answers_when_there_is_nothing_to_resume():
    import app as app_module

    response = app_module.app.test_client().get("/ebook-workspaces/in-progress")
    assert response.status_code == 200
    assert isinstance(response.get_json()["projects"], list)


def test_the_route_stays_behind_the_invite_gate(monkeypatch):
    """A new route must not become a hole in the private-beta gate."""
    import app as app_module

    monkeypatch.setattr(app_module, "_invite_code_required", lambda: "a-code")
    assert app_module.app.test_client().get(
        "/ebook-workspaces/in-progress").status_code == 401
    assert "/ebook-workspaces/in-progress" not in app_module._INVITE_EXEMPT_PATHS
