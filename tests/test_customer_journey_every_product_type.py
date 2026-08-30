"""One end-to-end customer journey per product type.

The gap this closes
-------------------
On 2026-08-29 a customer clicked Build This Product, got an ebook, and could
not save it: no PDF, no ZIP, and no Editor-in-Chief verdict. 1047 tests passed
while that was true. The suite tested components exhaustively -- the routing,
the reviewer, the exporter -- but nothing tested the *promise*: a customer who
builds a product ends up with a finished, reviewed, downloadable artifact.

So this file asserts the promise, once per product type, over the real HTTP
routes a browser uses:

    generate -> save -> export -> download PDF + ZIP

and then checks the three things that made the failure invisible:

  * the export actually produced BOTH a PDF and a ZIP that download and open,
  * the bytes served match the recorded sha256 (not a stale package),
  * an Editor-in-Chief verdict is RECORDED -- absence is a failure, not silence.

A new product type must be added to PRODUCT_JOURNEYS. A type that cannot make
that trip is not ready to sell, which is the whole point of the check.

Zero paid/external calls: FACTORY_TEST_MODE plus conftest's network guard, and
every journey asserts the paid-call surfaces were never touched.
"""
from __future__ import annotations

import base64
import hashlib
import os
import sys
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

os.environ["FACTORY_TEST_MODE"] = "1"
os.environ["OPENAI_API_KEY"] = ""
os.environ["TAVILY_API_KEY"] = ""
os.environ["AI_INTEGRATIONS_OPENAI_API_KEY"] = ""
os.environ["PEXELS_API_KEY"] = ""

from app import app  # noqa: E402
import database  # noqa: E402


# One entry per SELLABLE product type.
#
#   fields     -- the minimum that builds a real artifact with no paid call.
#                 "Basic Test Fallback" keeps the coloring book off the image API.
#   review_key -- the review this type is expected to carry once exported.
#                 Pinned per type rather than "any review", so a product that
#                 silently loses its reviewer fails here instead of shipping
#                 unreviewed. Ebooks and planners get the Editor-in-Chief;
#                 puzzles and worksheets get the product QA agent's qa_report.
#
# Hidden/not-yet-public types (spelling_worksheet, planner, flip_book,
# cover_design, marketing_kit) are deliberately absent -- /generate-product
# refuses them, which HiddenProductTypesStayHiddenTests pins separately.
PRODUCT_JOURNEYS: dict[str, dict] = {
    "word_search": {
        "fields": {
            "topic": "Ocean Animals",
            "puzzles": "2",
            "difficulty": "Easy",
            "audience": "kids 8-12",
        },
        "review_key": "qa_report",
    },
    "crossword": {
        "fields": {
            "theme": "Ocean Animals",
            "puzzles": "2",
            "difficulty": "Easy",
            "audience": "kids 8-12",
        },
        "review_key": "qa_report",
    },
    "coloring_book": {
        "fields": {
            "coloring_title": "Sea Creatures",
            "theme": "deep sea ocean creatures",
            "output_format": "Digital Book",
            "quality_mode": "Basic Test Fallback",
            "art_style": "Cartoon comic-book",
            "age_group": "Children ages 8-12",
            "pages": "4",
            "include_captions": "No",
        },
        # Not qa_report: the coloring book records its own review under
        # qa_result/qa_passed. Three different key names across the catalogue
        # (qa_report, qa_result, editor_in_chief) is why "is this reviewed?"
        # was not an easy question to answer.
        "review_key": "qa_result",
    },
    "math_worksheet": {
        "fields": {
            "topic": "addition",
            "grade": "3",
            "pages": "2",
            "audience": "grade 3",
        },
        "review_key": "qa_report",
    },
    "faith_planner": {
        "fields": {"pages": "24", "theme": "Family"},
        "review_key": "editor_in_chief",
    },
    "budget_planner": {
        "fields": {"pages": "24"},
        "review_key": "editor_in_chief",
    },
}

# Refused by /generate-product until they are finished. Listed so that quietly
# exposing one to customers has to be a deliberate edit here.
HIDDEN_PRODUCT_TYPES = (
    "marketing_kit",
    "cover_design",
    "flip_book",
    "planner",
    "spelling_worksheet",
)


class CustomerJourneyPerProductTypeTests(unittest.TestCase):
    """Every sellable product type must survive the whole customer trip."""

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()
        self._created_ids: list[int] = []

    def tearDown(self):
        for pid in self._created_ids:
            try:
                database.delete_project(pid)
            except Exception:  # noqa: BLE001
                pass

    # -- the journey ---------------------------------------------------- //
    def _generate(self, product_type: str, fields: dict) -> dict:
        resp = self.client.post(
            "/generate-product", json={"product_type": product_type, "fields": fields}
        )
        self.assertEqual(
            resp.status_code, 200,
            f"{product_type}: /generate-product failed: {resp.data[:400]}")
        preview = resp.get_json()
        self.assertEqual(preview.get("product_type"), product_type)
        pdf_b64 = preview.get("pdf_bytes")
        self.assertTrue(pdf_b64, f"{product_type}: preview carried no PDF bytes")
        self.assertTrue(
            base64.b64decode(pdf_b64).startswith(b"%PDF"),
            f"{product_type}: preview bytes are not a PDF")
        return preview

    def _save(self, product_type: str, preview: dict) -> int:
        resp = self.client.post(
            "/projects",
            json={
                "name": preview.get("title") or f"Journey {product_type}",
                "type": "product",
                "user_saved": True,
                "temporary": True,
                "system_test": True,
                "data": dict(preview),
            },
        )
        self.assertEqual(
            resp.status_code, 201,
            f"{product_type}: saving the product failed: {resp.data[:400]}")
        project_id = resp.get_json()["id"]
        self._created_ids.append(project_id)
        return project_id

    def _export(self, product_type: str, project_id: int) -> dict:
        resp = self.client.post("/export-product", json={"project_id": project_id})
        self.assertEqual(
            resp.status_code, 200,
            f"{product_type}: /export-product failed: {resp.data[:400]}")
        return resp.get_json()

    def _assert_downloadable(self, product_type: str, export_body: dict) -> None:
        files = (export_body.get("exports") or {}).get("files") or {}
        for kind in ("pdf", "zip"):
            self.assertIn(
                kind, files,
                f"{product_type}: export produced no {kind.upper()} -- the customer "
                f"cannot save this product")
            self.assertTrue(
                files[kind].get("url"), f"{product_type}: {kind} has no download url")
            self.assertTrue(
                files[kind].get("sha256"), f"{product_type}: {kind} has no sha256")

        pdf_dl = self.client.get(files["pdf"]["url"])
        zip_dl = self.client.get(files["zip"]["url"])
        self.assertEqual(
            pdf_dl.status_code, 200,
            f"{product_type}: PDF download refused: {pdf_dl.data[:300]}")
        self.assertEqual(
            zip_dl.status_code, 200,
            f"{product_type}: ZIP download refused: {zip_dl.data[:300]}")

        self.assertTrue(
            pdf_dl.data.startswith(b"%PDF"), f"{product_type}: served file is not a PDF")
        self.assertGreater(len(pdf_dl.data), 100, f"{product_type}: PDF is empty")
        # The bytes served must be the bytes that were certified, or the
        # customer is downloading something nobody reviewed.
        self.assertEqual(
            hashlib.sha256(pdf_dl.data).hexdigest(), files["pdf"]["sha256"],
            f"{product_type}: served PDF does not match its recorded sha256")
        self.assertEqual(
            hashlib.sha256(zip_dl.data).hexdigest(), files["zip"]["sha256"],
            f"{product_type}: served ZIP does not match its recorded sha256")

        archive = zipfile.ZipFile(BytesIO(zip_dl.data))
        names = archive.namelist()
        self.assertTrue(names, f"{product_type}: the ZIP is empty")
        pdfs = [n for n in names if n.lower().endswith(".pdf")]
        self.assertTrue(
            pdfs, f"{product_type}: the ZIP contains no PDF (files: {names[:8]})")
        self.assertTrue(
            archive.read(pdfs[0]).startswith(b"%PDF"),
            f"{product_type}: the PDF inside the ZIP is not a PDF")

    # -- the tests ------------------------------------------------------ //
    def test_every_product_type_completes_the_customer_journey(self):
        """generate -> save -> export -> download, for each type."""
        for product_type, spec in PRODUCT_JOURNEYS.items():
            with self.subTest(product_type=product_type):
                preview = self._generate(product_type, spec["fields"])
                project_id = self._save(product_type, preview)
                export_body = self._export(product_type, project_id)
                self._assert_downloadable(product_type, export_body)

    def test_every_product_type_is_reviewed_before_it_can_be_sold(self):
        """A finished product carries the review its type is supposed to get.

        The 2026-08-29 ebook had no `editor_in_chief` key at all, and nothing
        anywhere treated that absence as a problem -- it simply looked done.
        Silence is the failure mode being tested for here, so the expected
        reviewer is pinned per type: losing it is a failure, not a shrug.
        """
        for product_type, spec in PRODUCT_JOURNEYS.items():
            with self.subTest(product_type=product_type):
                preview = self._generate(product_type, spec["fields"])
                project_id = self._save(product_type, preview)
                self._export(product_type, project_id)

                stored = (self.client.get(f"/projects/{project_id}").get_json()
                          or {}).get("data") or {}
                # Name only the review-ish keys -- the full record is megabytes
                # of PDF metadata and would bury the actual failure.
                found = sorted(
                    k for k in stored if "qa" in k or "editor" in k or "review" in k)
                self.assertIn(
                    spec["review_key"], stored,
                    f"{product_type}: exported with no {spec['review_key']}; an "
                    f"unreviewed product must never look finished. "
                    f"Review keys present: {found or 'NONE'}")

    def test_the_journey_never_reaches_a_paid_provider(self):
        """The whole trip must stay free, or it cannot run in the gate."""
        with patch("ai_client.chat", side_effect=AssertionError("paid chat")), \
             patch("ai_client.chat_json", side_effect=AssertionError("paid chat_json")):
            for product_type, spec in PRODUCT_JOURNEYS.items():
                with self.subTest(product_type=product_type):
                    preview = self._generate(product_type, spec["fields"])
                    project_id = self._save(product_type, preview)
                    self._export(product_type, project_id)

    def test_hidden_product_types_are_refused_to_customers(self):
        """A type that is not finished must not be buildable from the UI."""
        for product_type in HIDDEN_PRODUCT_TYPES:
            with self.subTest(product_type=product_type):
                resp = self.client.post(
                    "/generate-product",
                    json={"product_type": product_type, "fields": {"pages": "4"}},
                )
                self.assertEqual(
                    resp.status_code, 400,
                    f"{product_type} is hidden but /generate-product accepted it")

    def test_every_sellable_builder_has_a_journey(self):
        """A new sellable product type cannot ship without a journey here.

        This is the part that makes the file self-maintaining: adding a builder
        to ACTIVE_BUILDERS without proving it can complete the trip fails.
        """
        from services.factory_advantage import ACTIVE_BUILDERS

        # Ebook is covered by its own workspace journey (see the ebook
        # customer-path suites); everything else must appear here.
        expected = {fid for fid in ACTIVE_BUILDERS.values() if fid != "ebook"}
        missing = expected - set(PRODUCT_JOURNEYS)
        self.assertEqual(
            missing, set(),
            f"these sellable product types have no end-to-end journey: "
            f"{sorted(missing)} -- add them to PRODUCT_JOURNEYS")


class EbookBuildEntryPointTests(unittest.TestCase):
    """Build This Product must send an ebook down the exportable pipeline.

    The ebook is the one type whose full journey lives elsewhere -- the real
    browser walks manuscript -> visuals -> cover -> preflight -> export ->
    PDF + ZIP in test_ebook_real_browser_customer_path.py, and that has always
    passed. What was never tested is the ENTRY POINT, and that is exactly
    where the 2026-08-29 failure lived: Build This Product called runEbook(),
    which POSTs /generate-ebook -- the legacy one-shot generator. It cannot
    export, so the customer got prose with no PDF, no ZIP, and no reviewer.

    These tests pin the entry point rather than re-walking the journey.
    """

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()
        self._created_ids: list[int] = []

    def tearDown(self):
        for pid in self._created_ids:
            try:
                database.delete_project(pid)
            except Exception:  # noqa: BLE001
                pass

    # There is more than one way into the ebook builder, and checking only one
    # is how the first attempt at this fix missed. sendToBuilder() serves the
    # saved-plan button; buildThisProduct() serves Factory Market Advantage's
    # Build This Product -- the one a customer actually clicks after research.
    # Both must reach the exportable pipeline, so both are pinned here.
    EBOOK_ENTRY_POINTS = (
        ("sendToBuilder", "async function sendToBuilder(", '"ebook"', "// Active other"),
        ("buildThisProduct", "async function buildThisProduct(", 'factoryId === "ebook"', 'go("factory")'),
    )

    def _entry_branch(self, start_marker: str, split_on: str, end_marker: str) -> str:
        source = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        body = source.split(start_marker, 1)[1]
        branch = body.split(split_on, 1)[1]
        return branch.split(end_marker, 1)[0]

    def test_every_ebook_entry_point_starts_a_workspace(self):
        for name, start, split_on, end in self.EBOOK_ENTRY_POINTS:
            with self.subTest(entry_point=name):
                branch = self._entry_branch(start, split_on, end)
                self.assertIn(
                    '"/ebook-workspace"', branch,
                    f"{name}() no longer creates an Ebook Project workspace")
                self.assertIn(
                    "openEbookWorkspace(", branch,
                    f"{name}() creates a workspace but never opens it")

    def test_no_ebook_entry_point_uses_the_legacy_builder(self):
        """services/ebook.py: 'LEGACY ... Cannot create Export Ready ebooks.'

        Landing on the Ebook Builder view is the problem, not just calling
        runEbook(): the Builder's own generate button POSTs /generate-ebook,
        so `go("ebook")` hands the customer a dead end either way.
        """
        for name, start, split_on, end in self.EBOOK_ENTRY_POINTS:
            with self.subTest(entry_point=name):
                branch = self._entry_branch(start, split_on, end)
                self.assertNotIn(
                    "runEbook()", branch,
                    f"{name}() fires the legacy one-shot generator; it cannot "
                    f"produce a PDF, a ZIP, or an Editor-in-Chief review")
                self.assertNotIn(
                    'go("ebook")', branch,
                    f"{name}() drops the customer in the legacy Ebook Builder, "
                    f"whose generate button cannot produce an exportable book")

    def test_a_new_workspace_is_on_the_exportable_pipeline(self):
        resp = self.client.post(
            "/ebook-workspace",
            json={
                "topic": "Zero-waste weekly meal planning",
                "author": "Journey Test",
                "audience": "busy families",
                "outcome": "waste less food",
            },
        )
        self.assertEqual(resp.status_code, 200, resp.data[:300])
        body = resp.get_json() or {}
        project_id = (body.get("project") or {}).get("id")
        self.assertIsNotNone(project_id, "no project was created")
        self._created_ids.append(project_id)

        stored = (self.client.get(f"/projects/{project_id}").get_json()
                  or {}).get("data") or {}
        self.assertTrue(
            stored.get("ebook_project_workspace"),
            "the created project is not an Ebook Project workspace")
        self.assertIn(
            "ebook_workspace", stored,
            "the project has no workspace state, so it cannot walk the pipeline")
        # A brand-new book must not claim to be sellable before it is built
        # and reviewed -- that claim is what has to be earned at export.
        self.assertFalse(
            stored.get("export_ready"),
            "a workspace claims export_ready before anything has been built")

    def test_the_legacy_generator_cannot_reach_export(self):
        """Characterises WHY the legacy path is unfit, so nobody re-adopts it.

        The release validator already refuses it. That refusal was invisible
        to the customer, who simply saw a book with no download.
        """
        legacy = {
            "product_type": "ebook",
            "legacy_oneshot": True,
            "title": "Legacy one-shot book",
            "content": "Some prose but no chapters, cover, or package.",
            "ebook": "Some prose but no chapters, cover, or package.",
        }
        saved = self.client.post(
            "/projects",
            json={
                "name": "Legacy one-shot book",
                "type": "ebook",
                "user_saved": True,
                "temporary": True,
                "system_test": True,
                "data": legacy,
            },
        ).get_json()
        project_id = saved["id"]
        self._created_ids.append(project_id)

        resp = self.client.post("/export-product", json={"project_id": project_id})
        self.assertNotEqual(
            resp.status_code, 200,
            "a legacy one-shot ebook exported successfully -- if this now works, "
            "the customer-facing story has changed and this test should be revisited")

        stored = (self.client.get(f"/projects/{project_id}").get_json()
                  or {}).get("data") or {}
        self.assertFalse(
            stored.get("export_ready"),
            "a book that cannot export must never be marked export_ready")


if __name__ == "__main__":
    unittest.main()
