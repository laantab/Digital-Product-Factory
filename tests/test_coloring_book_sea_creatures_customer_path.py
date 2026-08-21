"""Sea Creatures coloring-book customer path — mocked, zero paid calls.

Regression: cover appeared, then the complete book vanished from the customer
path because artifact_state=DRAFT was treated as an unfinished draft.
"""
from __future__ import annotations

import hashlib
import io
import os
import shutil
import sys
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from tests._test_paths import resolve_test_exports_root  # noqa: E402

os.environ["FACTORY_TEST_MODE"] = "1"
os.environ["OPENAI_API_KEY"] = ""
os.environ["TAVILY_API_KEY"] = ""
os.environ["AI_INTEGRATIONS_OPENAI_API_KEY"] = ""
os.environ["PEXELS_API_KEY"] = ""

from app import app  # noqa: E402
import database  # noqa: E402


SEA_FIELDS = {
    "coloring_title": "Sea Creatures",
    "theme": "create a coloring page with deep sea oceans creatures",
    "output_format": "Digital Book",
    "quality_mode": "Basic Test Fallback",
    "art_style": "Cartoon comic-book",
    "age_group": "Children ages 8–12",
    "pages": "12",
    "include_captions": "No",
}

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class SeaCreaturesColoringBookCustomerPathTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True
        self._created_ids: list[int] = []
        self._export_dirs: list[Path] = []
        self._img_patch = patch(
            "services.coloring_book.builder.generate_visual_image",
            side_effect=AssertionError("No paid image calls"),
        )
        self._chat_patch = patch(
            "services.coloring_book.builder.chat_json",
            side_effect=AssertionError("No paid chat calls"),
        )
        self._img_patch.start()
        self._chat_patch.start()
        self.addCleanup(self._img_patch.stop)
        self.addCleanup(self._chat_patch.stop)

    def tearDown(self):
        for pid in self._created_ids:
            try:
                database.delete_project(pid)
            except Exception:
                pass
        for folder in self._export_dirs:
            shutil.rmtree(folder, ignore_errors=True)

    def _track_pkg(self, package_id: str | None):
        if package_id:
            self._export_dirs.append(resolve_test_exports_root() / str(package_id))

    def _generate(self, extra_fields=None):
        fields = dict(SEA_FIELDS)
        if extra_fields:
            fields.update(extra_fields)
        resp = self.client.post(
            "/generate-product",
            json={"product_type": "coloring_book", "fields": fields},
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        body = resp.get_json()
        self.assertIsInstance(body, dict)
        self._track_pkg(body.get("package_id"))
        return body

    def test_submit_cover_interiors_qa_save_reopen_pdf_zip(self):
        cover = self._generate({"generation_stage": "cover_preview"})
        self.assertEqual(cover.get("product_type"), "coloring_book")
        self.assertEqual(cover.get("generation_stage"), "cover_preview")
        self.assertTrue(cover.get("needs_approval"))
        self.assertTrue(cover.get("package_id"))
        pkg = str(cover["package_id"])
        pkg_dir = resolve_test_exports_root() / pkg
        self.assertTrue(
            (pkg_dir / "img_cover.png").is_file() or (pkg_dir / "cover.png").is_file(),
            "cover image missing",
        )

        sample = self._generate(
            {
                "generation_stage": "sample_interior",
                "package_id": pkg,
                "character_approved": "true",
            }
        )
        self.assertEqual(sample.get("generation_stage"), "sample_interior")
        self.assertTrue(sample.get("needs_approval"))
        self.assertTrue((pkg_dir / "img_cover.png").is_file() or (pkg_dir / "cover.png").is_file())

        full = self._generate(
            {
                "generation_stage": "full",
                "package_id": pkg,
                "character_approved": "true",
                "sample_approved": "true",
            }
        )
        self.assertEqual(full.get("generation_stage"), "full")
        self.assertFalse(full.get("needs_approval"))
        pages = full.get("pages") or []
        self.assertGreaterEqual(len(pages), 12, "required interior pages missing")
        qa = full.get("qa_result") or {}
        self.assertTrue(qa.get("all_passed") or full.get("qa_passed") is not False)
        self.assertFalse(qa.get("blocked_export"))
        self.assertEqual(full.get("artifact_state"), "DRAFT")
        self.assertTrue(full.get("pdf_bytes") or (pkg_dir / str(full.get("filename") or "")).is_file())

        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("data-coloring-interior-preview", js)
        self.assertIn("data-coloring-interior-missing", js)
        self.assertIn("_coloringInteriorPreviewEntries", js)
        self.assertIn("data-kdp-coloring-interiors", js)
        self.assertIn("Your cover stays on this page while the next step runs", js)
        self.assertIn("_coloringBookCustomerReady", js)
        self.assertIn("if (!_coloringBookPendingApproval(data) && _coloringBookCustomerReady(data))", js)

        payload = dict(full)
        payload.pop("pdf_bytes", None)
        payload["pdf_stored_on_disk"] = True
        payload["user_confirmed_save"] = True
        payload["stage"] = "product_generated"
        save = self.client.post(
            "/projects",
            json={
                "name": full.get("title") or "Sea Creatures",
                "type": "product",
                "data": payload,
                "user_saved": True,
                "user_confirmed_save": True,
            },
        )
        self.assertEqual(save.status_code, 201, save.data)
        saved = save.get_json()
        pid = int(saved["id"])
        self._created_ids.append(pid)
        saved_data = saved.get("data") or {}
        self.assertEqual(saved_data.get("package_id"), pkg)
        self.assertEqual(saved_data.get("generation_stage"), "full")

        listed = self.client.get("/projects").get_json() or []
        ids = {int(p["id"]) for p in listed}
        names = [p.get("name") or "" for p in listed]
        self.assertIn(pid, ids)
        self.assertTrue(any("sea" in n.lower() and "creature" in n.lower() for n in names))

        opened = self.client.get(f"/projects/{pid}")
        self.assertEqual(opened.status_code, 200, opened.data)
        odata = (opened.get_json() or {}).get("data") or {}
        self.assertEqual(odata.get("package_id"), pkg)
        self.assertEqual(len(odata.get("pages") or []), len(pages))
        self.assertEqual(odata.get("artifact_state"), "DRAFT")
        previews = odata.get("interior_previews") or []
        self.assertEqual(len(previews), len(pages))
        self.assertTrue(odata.get("cover_preview_url"))
        cover_dl = self.client.get(str(odata["cover_preview_url"]))
        self.assertEqual(cover_dl.status_code, 200, cover_dl.data)
        self.assertTrue(str(cover_dl.mimetype or "").startswith("image/"))
        page0 = (odata.get("pages") or [{}])[0]
        self.assertNotIn("preview_url", page0)
        has_interior_png = (pkg_dir / "coloring_p01.png").is_file()
        if has_interior_png:
            for pr in previews:
                self.assertFalse(pr.get("missing"), pr)
                self.assertTrue(str(pr.get("url") or "").startswith("/projects/"))
                img = self.client.get(str(pr["url"]))
                self.assertEqual(img.status_code, 200, pr)
                self.assertTrue(str(img.mimetype or "").startswith("image/"), img.mimetype)
                self.assertNotIn(
                    "attachment",
                    str(img.headers.get("Content-Disposition") or "").lower(),
                )
            pkg_img = self.client.get(f"/download/{pkg}/coloring_p01.png")
            self.assertEqual(pkg_img.status_code, 200, pkg_img.data)
        else:
            for pr in previews:
                self.assertTrue(pr.get("missing"), pr)

        pdf_path = pkg_dir / str(full.get("filename") or "sea_creatures.pdf")
        if not pdf_path.is_file():
            pdfs = list(pkg_dir.glob("*.pdf"))
            self.assertTrue(pdfs, "generated PDF missing on disk")
            pdf_path = pdfs[0]
        before_pdf = pdf_path.read_bytes()
        self.assertTrue(before_pdf.startswith(b"%PDF"))
        before_hash = _sha256(before_pdf)

        export = self.client.post("/export-product", json={"project_id": pid})
        self.assertEqual(export.status_code, 200, export.data)
        files = ((export.get_json() or {}).get("exports") or {}).get("files") or {}
        self.assertIn("pdf", files)
        self.assertIn("zip", files)
        pdf_url = files["pdf"]["url"]
        zip_url = files["zip"]["url"]
        pdf_dl = self.client.get(pdf_url)
        zip_dl = self.client.get(zip_url)
        self.assertEqual(pdf_dl.status_code, 200, pdf_dl.data)
        self.assertEqual(zip_dl.status_code, 200, zip_dl.data)
        self.assertTrue(pdf_dl.data.startswith(b"%PDF"))
        self.assertEqual(_sha256(pdf_dl.data), before_hash)
        zf = zipfile.ZipFile(io.BytesIO(zip_dl.data))
        names_in_zip = zf.namelist()
        pdf_members = [n for n in names_in_zip if n.lower().endswith(".pdf")]
        self.assertTrue(pdf_members, names_in_zip)
        zip_pdf = zf.read(pdf_members[0])
        self.assertEqual(_sha256(zip_pdf), before_hash)
        after_pdf = pdf_path.read_bytes()
        self.assertEqual(_sha256(after_pdf), before_hash)

    def test_cover_preview_save_is_not_customer_complete(self):
        cover = self._generate({"generation_stage": "cover_preview"})
        payload = dict(cover)
        payload.pop("pdf_bytes", None)
        payload["pdf_stored_on_disk"] = True
        payload["user_confirmed_save"] = True
        payload["stage"] = "product_generated"
        payload["artifact_state"] = "DRAFT"
        save = self.client.post(
            "/projects",
            json={
                "name": "Sea Creatures Cover Preview Must Hide",
                "type": "product",
                "data": payload,
                "user_saved": True,
                "user_confirmed_save": True,
            },
        )
        self.assertEqual(save.status_code, 201, save.data)
        pid = int(save.get_json()["id"])
        self._created_ids.append(pid)
        listed = self.client.get("/projects").get_json() or []
        self.assertNotIn(pid, {int(p["id"]) for p in listed})
        self.assertIsNotNone(database.get_project(pid))

    def test_qa_failure_preserves_assets_and_blocks_save_list(self):
        full = self._generate({"generation_stage": "full"})
        pkg = str(full["package_id"])
        pkg_dir = resolve_test_exports_root() / pkg
        cover_before = list(pkg_dir.glob("*.png"))
        self.assertTrue(cover_before)

        payload = dict(full)
        payload.pop("pdf_bytes", None)
        payload["pdf_stored_on_disk"] = True
        payload["user_confirmed_save"] = True
        payload["stage"] = "product_generated"
        payload["artifact_state"] = "DRAFT"
        payload["qa_passed"] = False
        payload["qa_result"] = {
            "all_passed": False,
            "blocked_export": True,
            "errors": ["interior QA failed on fixture"],
        }
        save = self.client.post(
            "/projects",
            json={
                "name": "Sea Creatures QA Blocked Fixture",
                "type": "product",
                "data": payload,
                "user_saved": True,
                "user_confirmed_save": True,
            },
        )
        self.assertEqual(save.status_code, 201, save.data)
        pid = int(save.get_json()["id"])
        self._created_ids.append(pid)
        listed = self.client.get("/projects").get_json() or []
        self.assertNotIn(pid, {int(p["id"]) for p in listed})
        stored = database.get_project(pid)
        self.assertIsNotNone(stored)
        self.assertTrue(pkg_dir.is_dir())
        self.assertTrue(list(pkg_dir.glob("*.png")))
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("What was preserved", js)
        self.assertIn("The form was not cleared", js)
        self.assertIn("Save Product (complete the book first)", js)

    def test_thunder_volt_lock_untouched(self):
        lock = ROOT / "COLORING_BOOK_THUNDER_VOLT_LOCKED_STATE.md"
        self.assertTrue(lock.is_file())
        pkg = resolve_test_exports_root() / "a092b8e351174900a9082fbb46350364"
        if pkg.is_dir():
            pdf = pkg / "thunder_volt.pdf"
            zpath = pkg / "package.zip"
            self.assertTrue(pdf.is_file())
            self.assertTrue(zpath.is_file())
            self.assertGreater(pdf.stat().st_size, 1000)
            self.assertGreater(zpath.stat().st_size, 1000)


class SeaCreaturesColoringBookAuthorTests(unittest.TestCase):
    """Author must appear on coloring payload, preview, and retail cover/PDF."""

    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True
        self._created_ids: list[int] = []
        self._export_dirs: list[Path] = []
        self._img_patch = patch(
            "services.coloring_book.builder.generate_visual_image",
            side_effect=AssertionError("No paid image calls"),
        )
        self._chat_patch = patch(
            "services.coloring_book.builder.chat_json",
            side_effect=AssertionError("No paid chat calls"),
        )
        self._img_patch.start()
        self._chat_patch.start()
        self.addCleanup(self._img_patch.stop)
        self.addCleanup(self._chat_patch.stop)

    def tearDown(self):
        for pid in self._created_ids:
            try:
                database.delete_project(pid)
            except Exception:
                pass
        for folder in self._export_dirs:
            shutil.rmtree(folder, ignore_errors=True)

    def test_form_has_author_input(self):
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id: "coloring_book"', js)
        coloring_block = js.split('id: "coloring_book"', 1)[1].split('id: "word_search"', 1)[0]
        self.assertIn('name: "author_brand"', coloring_block)
        self.assertIn("Author name", coloring_block)
        self.assertIn("Lonnie Brown", coloring_block)
        self.assertIn("function _productAuthor", js)
        self.assertIn("data-coloring-author-byline", js)

    def test_payload_preview_and_pdf_include_author(self):
        import fitz

        fields = dict(SEA_FIELDS)
        resp = self.client.post(
            "/generate-product",
            json={"product_type": "coloring_book", "fields": fields},
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        body = resp.get_json()
        self.assertIsInstance(body, dict)
        if body.get("package_id"):
            self._export_dirs.append(resolve_test_exports_root() / str(body["package_id"]))
        self.assertEqual(body.get("author"), "Lonnie Brown")
        self.assertEqual(body.get("author_name"), "Lonnie Brown")
        self.assertEqual(body.get("author_brand"), "Lonnie Brown")
        self.assertIn("Lonnie Brown", str(body.get("author_byline") or ""))
        self.assertEqual((body.get("fields") or {}).get("author_brand"), "Lonnie Brown")
        cover = body.get("cover_design") or {}
        self.assertEqual(cover.get("author"), "Lonnie Brown")
        self.assertNotEqual(cover.get("overlay_style"), "clean_title")

        pdf_bytes = body.get("pdf_bytes") or ""
        self.assertTrue(pdf_bytes)
        raw = __import__("base64").b64decode(pdf_bytes)
        self.assertTrue(raw.startswith(b"%PDF"))
        doc = fitz.open(stream=raw, filetype="pdf")
        cover_text = (doc[0].get_text("text") or "")
        meta = doc.metadata or {}
        doc.close()
        self.assertIn("Lonnie Brown", cover_text)
        self.assertIn("Lonnie Brown", str(meta.get("author") or ""))

        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("data-coloring-author-byline", js)
        kdp_src = js[js.find('data-kdp="author"') : js.find('data-kdp="author"') + 180]
        self.assertIn("_productAuthor(d)", kdp_src)

    def test_17365_style_fixture_shows_author(self):
        import fitz
        from services.coloring_book.pdf_cover import apply_author_overlay_to_existing_coloring_book
        from services.coloring_book.prompt_engine import FACTORY_COLORING_AUTHOR

        fields = dict(SEA_FIELDS)
        fields["coloring_title"] = "Deep Sea Ocean Creatures"
        fields["theme"] = "create a coloring page with deep sea oceans creatures"
        fields["art_style"] = "Realistic"
        resp = self.client.post(
            "/generate-product",
            json={"product_type": "coloring_book", "fields": fields},
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        body = resp.get_json()
        pkg = str(body.get("package_id") or "")
        self.assertTrue(pkg)
        self._export_dirs.append(resolve_test_exports_root() / pkg)
        # Simulate a saved #17365-style record with author stripped.
        stripped = dict(body)
        stripped.pop("author", None)
        stripped.pop("author_name", None)
        stripped.pop("author_brand", None)
        stripped.pop("author_byline", None)
        stripped["fields"] = dict(stripped.get("fields") or {})
        stripped["fields"].pop("author", None)
        stripped["fields"].pop("author_brand", None)
        cover = dict(stripped.get("cover_design") or {})
        cover.pop("author", None)
        stripped["cover_design"] = cover
        stripped["pdf_bytes"] = None
        repaired = apply_author_overlay_to_existing_coloring_book(stripped)
        self.assertEqual(repaired.get("author"), FACTORY_COLORING_AUTHOR)
        self.assertEqual((repaired.get("cover_design") or {}).get("author"), FACTORY_COLORING_AUTHOR)
        pdf_path = resolve_test_exports_root() / pkg / str(body.get("filename") or "deep_sea_ocean_creatures.pdf")
        self.assertTrue(pdf_path.is_file(), pdf_path)
        doc = fitz.open(pdf_path)
        text = doc[0].get_text("text") or ""
        page_count = doc.page_count
        doc.close()
        self.assertIn(FACTORY_COLORING_AUTHOR, text)
        self.assertEqual(page_count, 13)
        preview = resolve_test_exports_root() / pkg / "cover_page_preview.png"
        self.assertTrue(preview.is_file())

    def test_thunder_volt_cover_does_not_draw_factory_author(self):
        import fitz
        from services.coloring_book.pdf_builder import (
            ColoringBookPdfRequest,
            build_coloring_book_pdf,
        )

        theme = (
            "Thunder Volt is a Black superhero. "
            "He is stopping two men from robbing a bank in New York City."
        )
        result = build_coloring_book_pdf(
            ColoringBookPdfRequest(
                product_title="THUNDER VOLT",
                theme=theme,
                page_count=2,
                include_cover=True,
                output_type="book",
                quality_mode="basic_test",
                package_id="tv_author_overlay_guard",
                generation_stage="full",
                author="Lonnie Brown",
            )
        )
        self.assertFalse(result.errors, result.errors)
        self._export_dirs.append(resolve_test_exports_root() / "tv_author_overlay_guard")
        self.assertEqual((result.cover_design or {}).get("overlay_style"), "clean_title")
        self.assertEqual((result.cover_design or {}).get("author"), "")
        doc = fitz.open(stream=result.pdf_bytes, filetype="pdf")
        text = (doc[0].get_text("text") or "")
        meta = doc.metadata or {}
        doc.close()
        self.assertNotIn("Lonnie Brown", text)
        self.assertEqual(meta.get("author"), "Digital Product Factory")

        lock_pdf = resolve_test_exports_root() / "a092b8e351174900a9082fbb46350364" / "thunder_volt.pdf"
        if lock_pdf.is_file():
            self.assertEqual(
                _sha256(lock_pdf.read_bytes()),
                "59c3d7cd0e22963cad995d762b4126f593ea97df2458577f80c431672aca4bac",
            )


if __name__ == "__main__":
    unittest.main()

