"""A half-written book must have a route back to it.

Reported 2026-09-02: "how do i get to zero-waste project". There was no answer.
Saved Projects lists only completed products with usable output
(``is_customer_saved_product``), which is right for a shelf of finished work —
but it meant an Ebook Project that was started and paid for, then left at
"needs correction", appeared **nowhere in the interface**. The customer could
not reopen their own draft.

This adds a "Still working on these" list. It is a query-time view only:
nothing is deleted, mutated, reclassified, or promoted onto the finished shelf.

Zero paid/external calls.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ["FACTORY_TEST_MODE"] = "1"

from app import app  # noqa: E402
import database  # noqa: E402
from services.ebook_project_workspace import (  # noqa: E402
    STATUS_APPROVED,
    STATUS_NEEDS_CORRECTION,
    ensure_workspace,
    new_workspace,
    set_stage_status,
)

APP_JS = ROOT / "static" / "js" / "app.js"
INDEX = ROOT / "templates" / "index.html"


def _make_workspace_project(name: str, *, finished: bool) -> int:
    data = ensure_workspace(
        {
            "title": name,
            "product_type": "ebook",
            "ebook_workspace": new_workspace(topic=name, audience="readers"),
        }
    )
    ws = data["ebook_workspace"]
    for stage in ("research", "title", "outline"):
        set_stage_status(ws, stage, STATUS_APPROVED)
    if finished:
        for stage in ("manuscript", "visuals", "cover", "design", "preview", "preflight", "export"):
            set_stage_status(ws, stage, STATUS_APPROVED)
    else:
        set_stage_status(ws, "manuscript", STATUS_NEEDS_CORRECTION)
    project = database.create_project(name, "ebook", data, user_saved=True)
    return int(project["id"])


class InProgressListingTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_an_unfinished_book_is_listed(self):
        pid = _make_workspace_project("Zero-Waste Meal Planning Starter Kit", finished=False)
        rows = database.list_in_progress_workspaces()
        self.assertIn(pid, [r["id"] for r in rows])

    def test_a_finished_book_is_not_listed_here(self):
        pid = _make_workspace_project("A Completely Finished Book", finished=True)
        rows = database.list_in_progress_workspaces()
        self.assertNotIn(
            pid,
            [r["id"] for r in rows],
            "a finished book belongs on the Saved Projects shelf, not in progress",
        )

    def test_each_row_says_where_the_book_is_and_what_is_next(self):
        _make_workspace_project("Weekly Reset Guide", finished=False)
        row = database.list_in_progress_workspaces()[0]
        for key in ("id", "name", "current_stage", "next_action", "stages_done", "stages_total"):
            with self.subTest(key=key):
                self.assertIn(key, row)
        self.assertGreaterEqual(row["stages_done"], 1)
        self.assertGreater(row["stages_total"], row["stages_done"])

    def test_the_listing_never_returns_the_stored_manuscript(self):
        """The list is a menu, not a payload: it must stay small."""
        _make_workspace_project("Another Draft", finished=False)
        row = database.list_in_progress_workspaces()[0]
        self.assertNotIn("data", row)
        self.assertNotIn("content", row)

    def test_the_route_serves_it(self):
        pid = _make_workspace_project("Routed Draft", finished=False)
        resp = self.client.get("/projects/in-progress")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(pid, [r["id"] for r in resp.get_json()])

    def test_the_limit_is_honoured(self):
        for i in range(3):
            _make_workspace_project(f"Draft {i}", finished=False)
        self.assertLessEqual(len(database.list_in_progress_workspaces(limit=2)), 2)
        resp = self.client.get("/projects/in-progress?limit=1")
        self.assertLessEqual(len(resp.get_json()), 1)

    def test_listing_does_not_change_any_project(self):
        pid = _make_workspace_project("Untouched Draft", finished=False)
        before = database.get_project(pid)
        database.list_in_progress_workspaces()
        self.client.get("/projects/in-progress")
        after = database.get_project(pid)
        self.assertEqual(before["data"], after["data"])
        self.assertEqual(before["updated_at"], after["updated_at"])

    def test_the_finished_shelf_is_unchanged_by_this(self):
        """Saved Projects must not start showing half-written books."""
        pid = _make_workspace_project("Half Written", finished=False)
        saved, _more = database.get_customer_saved_products(limit=10)
        self.assertNotIn(pid, [p["id"] for p in saved])


class InProgressUiTests(unittest.TestCase):
    def test_the_page_has_a_place_for_them(self):
        html = INDEX.read_text(encoding="utf-8")
        self.assertIn('id="inProgressWrap"', html)
        self.assertIn('id="inProgressList"', html)
        self.assertIn("Still working on these", html)
        # ...and the finished shelf is now labelled, so the two are distinct.
        self.assertIn("Finished products", html)

    def test_it_is_hidden_when_there_is_nothing_in_progress(self):
        html = INDEX.read_text(encoding="utf-8")
        wrap = html.split('id="inProgressWrap"', 1)[1].split(">", 1)[0]
        self.assertIn("hidden", wrap)
        js = APP_JS.read_text(encoding="utf-8")
        fn = js.split("async function renderInProgressProjects(", 1)[1].split(
            "const CUSTOMER_STEP_LABELS", 1
        )[0]
        self.assertIn('wrap.classList.add("hidden")', fn)

    def test_each_row_opens_the_workspace(self):
        js = APP_JS.read_text(encoding="utf-8")
        fn = js.split("async function renderInProgressProjects(", 1)[1].split(
            "const CUSTOMER_STEP_LABELS", 1
        )[0]
        self.assertIn("data-open-workspace", fn)
        self.assertIn("openEbookWorkspace(Number(btn.dataset.openWorkspace))", fn)
        self.assertIn("Continue", fn)

    def test_the_next_step_is_shown_in_plain_words(self):
        js = APP_JS.read_text(encoding="utf-8")
        table = js.split("const CUSTOMER_STEP_LABELS = {", 1)[1].split("};", 1)[0]
        self.assertIn("Write your chapters", table)
        self.assertIn("Fix one chapter", table)
        self.assertNotIn("generate_manuscript:", table.replace("generate_manuscript:", "", 1))

    def test_the_list_is_refreshed_with_saved_projects(self):
        js = APP_JS.read_text(encoding="utf-8")
        self.assertIn("renderInProgressProjects();", js)


if __name__ == "__main__":
    unittest.main()
