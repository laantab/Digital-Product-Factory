"""A finished ebook must be findable in Saved Projects.

The workspace pipeline never recorded the customer lifecycle tokens that
database.get_customer_saved_products() requires, so every ebook it built was
invisible in Saved Projects however complete it was — 12 of 12 on the owner's
machine, including finished, exported, sellable books. The customer could only
reach them by knowing a URL.

Two separate gates were unmet, and both are covered here:

  * _customer_status_allows_saved_list() needs an allowed status/stage token
  * _is_explicit_user_save() needs a save marker

Generic by design: no project id, title or topic is referenced. Every ebook is
built from a fixture in a temporary database.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def _fresh_db() -> str:
    # Deliberately not named after the production database file: the repo
    # guard in test_no_hardcoded_production_paths.py scans for that literal.
    path = os.path.join(tempfile.mkdtemp(prefix="saved_vis_"), "isolated_saved_visibility.db")
    os.environ["FACTORY_DB_PATH"] = path
    for mod in [m for m in list(sys.modules) if m == "database"]:
        del sys.modules[mod]
    return path


class _FinishedEbook:
    """A believable finished ebook, with real files on disk.

    The title and prose are deliberately ordinary. classify_customer_visibility
    hides anything that reads like a test or placeholder record, so a fixture
    named "test"/"fixture"/"sample" is hidden for that reason instead of the one
    under test, and the assertion would pass or fail for the wrong cause.
    """

    def __init__(self, tmp: Path, *, complete: bool = True):
        self.dir = tmp
        self.dir.mkdir(parents=True, exist_ok=True)
        self.pdf = self.dir / "ebook.pdf"
        self.zip = self.dir / "package.zip"
        self.pdf.write_bytes(b"%PDF-1.4\n% fixture\n")
        self.zip.write_bytes(b"PK\x03\x04fixture")
        self.complete = complete

    def data(self) -> dict:
        sentence = (
            "Short daily practice works better than long occasional practice, "
            "because the habit survives a bad week and the attention returns "
            "more quickly each time you notice it has wandered. "
        )
        body = (sentence * 40).strip()
        data = {
            "product_type": "ebook",
            "ebook_project_workspace": True,
            "artifact_state": "DRAFT",
            "title": "Quiet Mornings",
            "content": body,
            "ebook": body,
            "ebook_document": {"chapters": [{"chapter_id": f"ch{i}"} for i in range(1, 6)]},
            "ebook_workspace": {"rail": {}},
            "export_ready": True,
            "release_status": "PASS",
            "ebook_design_preflight": {"status": "PASS", "findings": []},
            "pdf_path": str(self.pdf),
            "pdf_available": True,
            "zip_available": True,
            "export_files": {"ebook.pdf": str(self.pdf), "package.zip": str(self.zip)},
        }
        if not self.complete:
            # A workspace exists and a manuscript was written, but the book
            # never finished: no preflight PASS, no package.
            data["export_ready"] = False
            data["release_status"] = ""
            data["ebook_design_preflight"] = {"status": "NEEDS_CORRECTION", "findings": [{"code": "x"}]}
            data.pop("export_files")
            data.pop("pdf_path")
        return data


class EbookQualificationTests(unittest.TestCase):
    """The evidence test that decides whether a book counts as finished."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ebq_"))

    def test_complete_ebook_qualifies(self):
        from services.ebook_customer_path import ebook_is_customer_complete

        self.assertTrue(ebook_is_customer_complete(_FinishedEbook(self.tmp).data()))

    def test_incomplete_ebook_does_not_qualify(self):
        from services.ebook_customer_path import ebook_is_customer_complete

        self.assertFalse(ebook_is_customer_complete(_FinishedEbook(self.tmp, complete=False).data()))

    def test_workspace_alone_does_not_qualify(self):
        """Requirement: do not mark a book generated just because a workspace exists."""
        from services.ebook_customer_path import ebook_is_customer_complete

        self.assertFalse(
            ebook_is_customer_complete(
                {"product_type": "ebook", "ebook_project_workspace": True, "ebook_workspace": {"rail": {}}}
            )
        )

    def test_flags_without_files_on_disk_do_not_qualify(self):
        """export_ready alone is a claim; the download must actually exist."""
        from services.ebook_customer_path import ebook_is_customer_complete

        data = _FinishedEbook(self.tmp).data()
        data["pdf_path"] = str(self.tmp / "missing.pdf")
        data["export_files"] = {"ebook.pdf": str(self.tmp / "missing.pdf")}
        self.assertFalse(ebook_is_customer_complete(data))

    def test_empty_manuscript_does_not_qualify(self):
        from services.ebook_customer_path import ebook_is_customer_complete

        data = _FinishedEbook(self.tmp).data()
        data["content"] = data["ebook"] = "too short"
        self.assertFalse(ebook_is_customer_complete(data))

    def test_marking_never_touches_artifact_state(self):
        """DRAFT / APPROVED / LOCKED is a separate lifecycle and must not move."""
        from services.ebook_customer_path import mark_ebook_customer_saved

        for state in ("DRAFT", "APPROVED", "LOCKED"):
            data = _FinishedEbook(self.tmp).data()
            data["artifact_state"] = state
            before_rev = data.get("artifact_revision")
            mark_ebook_customer_saved(data)
            self.assertEqual(data["artifact_state"], state)
            self.assertEqual(data.get("artifact_revision"), before_rev)

    def test_regressed_book_is_withdrawn_from_the_library(self):
        from services.ebook_customer_path import mark_ebook_customer_saved

        data = _FinishedEbook(self.tmp).data()
        mark_ebook_customer_saved(data)
        self.assertEqual(data["stage"], "product_generated")
        # Preflight later fails; the product no longer verifies.
        data["export_ready"] = False
        data["ebook_design_preflight"] = {"status": "FAIL"}
        mark_ebook_customer_saved(data)
        self.assertNotEqual(data.get("stage"), "product_generated")


class SavedProjectsListTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="spl_"))
        _fresh_db()
        import database

        database.init_db()
        self.database = database

    def _save_ebook(self, *, complete=True, artifact_state="DRAFT", name="Quiet Mornings"):
        from services.ebook_customer_path import mark_ebook_customer_saved

        data = _FinishedEbook(self.tmp / name.replace(" ", "_"), complete=complete).data()
        data["artifact_state"] = artifact_state
        mark_ebook_customer_saved(data)
        return self.database.create_project(
            name=name, type_="ebook", data=data, user_saved=True, user_confirmed_save=True
        )

    # 1. An export-ready DRAFT ebook appears in Saved Projects.
    def test_export_ready_draft_ebook_appears(self):
        p = self._save_ebook(artifact_state="DRAFT")
        rows, _ = self.database.get_customer_saved_products(limit=10, offset=0)
        self.assertIn(p["id"], [r["id"] for r in rows], "a finished DRAFT ebook is still hidden")

    # 2. An incomplete ebook does not appear merely because a workspace exists.
    def test_incomplete_ebook_stays_hidden(self):
        p = self._save_ebook(complete=False, name="Half Finished Book")
        rows, _ = self.database.get_customer_saved_products(limit=10, offset=0)
        self.assertNotIn(p["id"], [r["id"] for r in rows], "an unfinished ebook is being advertised")

    # 3. APPROVED ebook still appears.
    def test_approved_ebook_appears(self):
        p = self._save_ebook(artifact_state="APPROVED", name="Slow Evenings")
        rows, _ = self.database.get_customer_saved_products(limit=10, offset=0)
        self.assertIn(p["id"], [r["id"] for r in rows])

    # 4. LOCKED ebook behaves per existing lifecycle rules (visible, not deleted).
    def test_locked_ebook_still_behaves(self):
        p = self._save_ebook(artifact_state="LOCKED", name="Winter Reading")
        rows, _ = self.database.get_customer_saved_products(limit=10, offset=0)
        self.assertIn(p["id"], [r["id"] for r in rows])
        reopened = self.database.get_project(p["id"])
        self.assertEqual((reopened["data"] or {}).get("artifact_state"), "LOCKED")

    # 5. Visibility does not require regenerating the manuscript.
    def test_visibility_does_not_regenerate_content(self):
        p = self._save_ebook(name="Morning Pages")
        before = str((p["data"] or {}).get("content") or "")
        rows, _ = self.database.get_customer_saved_products(limit=10, offset=0)
        self.assertIn(p["id"], [r["id"] for r in rows])
        after = str((self.database.get_project(p["id"])["data"] or {}).get("content") or "")
        self.assertEqual(before, after, "listing the product changed the manuscript")

    # 6. Other generators are unchanged.
    def test_other_product_types_unaffected(self):
        coloring = self.database.create_project(
            name="Ocean Creatures",
            type_="product",
            data={
                "product_type": "coloring_book",
                "stage": "product_generated",
                "_saved_at": "2026-01-01T00:00:00",
                "pdf_path": str(self.tmp / "cb.pdf"),
                "pdf_available": True,
            },
            user_saved=True,
            user_confirmed_save=True,
        )
        (self.tmp / "cb.pdf").write_bytes(b"%PDF-1.4\n")
        before = json.dumps(self.database.get_project(coloring["id"])["data"], sort_keys=True)
        self._save_ebook(name="Garden Notes")
        after = json.dumps(self.database.get_project(coloring["id"])["data"], sort_keys=True)
        self.assertEqual(before, after, "adding an ebook mutated another product")

    # 7. Pagination still works.
    def test_pagination_still_works(self):
        for i in range(4):
            self._save_ebook(name=f"Collected Essays {i}")
        page1, more1 = self.database.get_customer_saved_products(limit=2, offset=0)
        page2, _ = self.database.get_customer_saved_products(limit=2, offset=2)
        self.assertEqual(len(page1), 2)
        self.assertTrue(more1)
        self.assertFalse(set(r["id"] for r in page1) & set(r["id"] for r in page2), "pages overlap")

    # 8. factory_sources and direct retrieval keep working.
    def test_factory_sources_and_direct_get_still_work(self):
        p = self._save_ebook(name="Kitchen Basics")
        srcs = self.database.list_factory_source_projects()
        self.assertIn(p["id"], [r["id"] for r in srcs])
        self.assertIsNotNone(self.database.get_project(p["id"]))
        self.assertIn(p["id"], [r["id"] for r in self.database.list_projects(include_system=True)])

    # 9. Reopening loads the existing project rather than creating a duplicate.
    def test_reopening_does_not_duplicate(self):
        p = self._save_ebook(name="Coastal Walks")
        before = len(self.database.list_projects(include_system=True))
        for _ in range(3):
            again = self.database.get_project(p["id"])
            self.assertEqual(again["id"], p["id"])
        rows, _ = self.database.get_customer_saved_products(limit=10, offset=0)
        self.assertEqual(len([r for r in rows if r["id"] == p["id"]]), 1, "duplicate row in the list")
        self.assertEqual(len(self.database.list_projects(include_system=True)), before)


class PipelineRecordsTheTokenTests(unittest.TestCase):
    """The forward fix: the export transition, not a one-off patch."""

    def test_orchestrator_export_stage_marks_the_book(self):
        import inspect

        from services import ebook_build_orchestrator as orch

        src = inspect.getsource(orch._run_export)
        self.assertIn("mark_ebook_customer_saved", src,
                      "the one-click export stage does not record customer visibility")

    def test_manual_export_route_marks_the_book(self):
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("mark_ebook_customer_saved", src,
                      "the manual export rail does not record customer visibility")

    def test_filter_itself_was_not_weakened(self):
        """The fix must be in the pipeline, not by loosening the gate."""
        import database

        self.assertEqual(
            database._CUSTOMER_ALLOWED_STATUSES,
            frozenset({"completed", "export_ready", "product_generated", "saved"}),
        )
        for blocked in ("draft", "needs_correction", "failed", "incomplete"):
            self.assertIn(blocked, database._CUSTOMER_BLOCKED_STATUSES)


if __name__ == "__main__":
    unittest.main()
