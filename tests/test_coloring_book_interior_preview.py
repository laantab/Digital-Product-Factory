"""Coloring-book interior preview URLs — mocked, zero paid calls.

Regression: titles showed after generate/reopen, but coloring_pNN.png was
rejected by /download (ebook img_* allowlist), so interior images 404'd.
"""
from __future__ import annotations

import base64
import hashlib
import os
import shutil
import sys
import unittest
from pathlib import Path

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
from services.coloring_book.preview_assets import (  # noqa: E402
    is_coloring_preview_filename,
)
from services.ebook_package import is_allowed_download  # noqa: E402

DEEP_SEA_TOPICS = [
    "Deep Sea Welcome",
    "Cave of Glowing Fish",
    "Jellyfish Garden",
    "Octopus Discovery",
    "Sea Turtle Passage",
    "Squid Spiral",
    "Reef of Strange Shapes",
    "Anglerfish Lantern Trail",
    "Whale Friend Below",
    "Crab and Clam Seafloor",
    "Circle of Ocean Friends",
    "Grand Deep Sea Panorama",
]

# 1x1 PNG
_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ColoringBookInteriorPreviewTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True
        self._created_ids: list[int] = []
        self._export_dirs: list[Path] = []

    def tearDown(self):
        for pid in self._created_ids:
            try:
                database.delete_project(pid)
            except Exception:
                pass
        for folder in self._export_dirs:
            shutil.rmtree(folder, ignore_errors=True)

    def _track_pkg(self, package_id: str) -> Path:
        folder = resolve_test_exports_root() / package_id
        folder.mkdir(parents=True, exist_ok=True)
        self._export_dirs.append(folder)
        return folder

    def _write_png(self, folder: Path, name: str) -> None:
        (folder / name).write_bytes(_TINY_PNG)

    def _save_coloring(self, *, pkg: str, topics: list[str], name: str = "Deep Sea Ocean Creatures"):
        pages = [
            {
                "page_number": i,
                "topic": topic,
                "caption": "",
                "line_art_prompt": "fixture",
                "image_path": str(resolve_test_exports_root() / pkg / f"coloring_p{i:02d}.png"),
            }
            for i, topic in enumerate(topics, start=1)
        ]
        payload = {
            "product_type": "coloring_book",
            "title": "Deep Sea Ocean Creatures",
            "package_id": pkg,
            "filename": "deep_sea_ocean_creatures.pdf",
            "pdf_stored_on_disk": True,
            "generation_stage": "full",
            "artifact_state": "DRAFT",
            "qa_passed": True,
            "pages": pages,
            "fields": {
                "coloring_title": "Deep Sea Ocean Creatures",
                "theme": "create a coloring page with deep sea oceans creatures",
                "pages": str(len(topics)),
                "output_format": "Digital Book",
            },
        }
        save = self.client.post(
            "/projects",
            json={
                "name": name,
                "type": "product",
                "data": payload,
                "user_saved": True,
                "user_confirmed_save": True,
            },
        )
        self.assertEqual(save.status_code, 201, save.data)
        pid = int(save.get_json()["id"])
        self._created_ids.append(pid)
        return pid

    def test_allowlist_keeps_ebook_img_pattern_and_allows_coloring_preview(self):
        self.assertFalse(is_allowed_download("coloring_p01.png"))
        self.assertFalse(is_allowed_download("cover_page_preview.png"))
        self.assertTrue(is_allowed_download("img_cover.png"))
        self.assertTrue(is_coloring_preview_filename("coloring_p01.png"))
        self.assertTrue(is_coloring_preview_filename("cover_page_preview.png"))
        self.assertTrue(is_coloring_preview_filename("img_cover.png"))
        self.assertFalse(is_coloring_preview_filename("../coloring_p01.png"))
        self.assertFalse(is_coloring_preview_filename("ebook.html"))

    def test_reopen_deep_sea_fixture_returns_resolving_interior_urls(self):
        pkg = "cb_preview_deep_sea_fixture"
        folder = self._track_pkg(pkg)
        self._write_png(folder, "img_cover.png")
        self._write_png(folder, "cover_page_preview.png")
        for i in range(1, 13):
            self._write_png(folder, f"coloring_p{i:02d}.png")
        pid = self._save_coloring(pkg=pkg, topics=DEEP_SEA_TOPICS)

        opened = self.client.get(f"/projects/{pid}")
        self.assertEqual(opened.status_code, 200, opened.data)
        odata = (opened.get_json() or {}).get("data") or {}
        previews = odata.get("interior_previews") or []
        self.assertEqual(len(previews), 12)
        self.assertEqual([p.get("topic") for p in previews], DEEP_SEA_TOPICS)
        self.assertTrue(odata.get("cover_preview_url"))
        self.assertFalse(odata.get("cover_preview_missing"))
        page0 = (odata.get("pages") or [{}])[0]
        self.assertNotIn("preview_url", page0)

        cover = self.client.get(str(odata["cover_preview_url"]))
        self.assertEqual(cover.status_code, 200, cover.data)
        self.assertEqual(cover.mimetype, "image/png")
        self.assertTrue(cover.data.startswith(b"\x89PNG"))
        self.assertNotIn("attachment", str(cover.headers.get("Content-Disposition") or "").lower())

        for pr in previews:
            self.assertFalse(pr.get("missing"), pr)
            url = str(pr.get("url") or "")
            self.assertTrue(url.startswith(f"/projects/{pid}/coloring-preview/"))
            img = self.client.get(url)
            self.assertEqual(img.status_code, 200, pr)
            self.assertEqual(img.mimetype, "image/png")
            self.assertTrue(img.data.startswith(b"\x89PNG"))
            self.assertNotIn("attachment", str(img.headers.get("Content-Disposition") or "").lower())

        dl = self.client.get(f"/download/{pkg}/coloring_p01.png")
        self.assertEqual(dl.status_code, 200, dl.data)
        self.assertEqual(dl.mimetype, "image/png")
        self.assertNotIn("attachment", str(dl.headers.get("Content-Disposition") or "").lower())

    def test_missing_interior_returns_clear_error_and_keeps_cover(self):
        pkg = "cb_preview_missing_page"
        folder = self._track_pkg(pkg)
        self._write_png(folder, "img_cover.png")
        self._write_png(folder, "cover_page_preview.png")
        self._write_png(folder, "coloring_p01.png")
        pid = self._save_coloring(
            pkg=pkg,
            topics=["Deep Sea Welcome", "Cave of Glowing Fish"],
            name="Deep Sea Missing Interior Fixture",
        )
        opened = self.client.get(f"/projects/{pid}")
        odata = (opened.get_json() or {}).get("data") or {}
        previews = odata.get("interior_previews") or []
        self.assertEqual(len(previews), 2)
        self.assertFalse(previews[0].get("missing"))
        self.assertTrue(previews[1].get("missing"))
        miss = self.client.get(previews[1]["url"])
        self.assertEqual(miss.status_code, 404, miss.data)
        body = miss.get_json() or {}
        self.assertIn("Interior page image missing", str(body.get("error") or miss.data))
        cover = self.client.get(str(odata["cover_preview_url"]))
        self.assertEqual(cover.status_code, 200, cover.data)

    def test_preview_html_includes_img_for_each_interior(self):
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function _coloringBookInteriorPreviewHtml", js)
        self.assertIn("function _coloringInteriorPreviewEntries", js)
        self.assertIn("data-coloring-interior-preview", js)
        self.assertIn("<img alt=", js)
        self.assertIn("data-coloring-interior-missing", js)
        self.assertIn("Interior page image missing", js)
        self.assertIn("data-kdp-coloring-interiors", js)
        self.assertIn("if (d.product_type === \"coloring_book\")", js)
        self.assertIn("_coloringBookFullCoverPreviewHtml(d)", js)
        self.assertNotIn("product_type === \"ebook\" && _coloringBookInteriorPreviewHtml", js)

    def test_other_product_get_payload_still_works(self):
        save = self.client.post(
            "/projects",
            json={
                "name": "Crossword GET Payload Still Works",
                "type": "product",
                "data": {
                    "product_type": "crossword",
                    "title": "Ocean Crossword",
                    "words": ["REEF", "CLAM"],
                },
                "user_saved": True,
                "user_confirmed_save": True,
            },
        )
        self.assertEqual(save.status_code, 201, save.data)
        pid = int(save.get_json()["id"])
        self._created_ids.append(pid)
        opened = self.client.get(f"/projects/{pid}")
        self.assertEqual(opened.status_code, 200, opened.data)
        odata = (opened.get_json() or {}).get("data") or {}
        self.assertEqual(odata.get("product_type"), "crossword")
        self.assertEqual(odata.get("words"), ["REEF", "CLAM"])
        self.assertNotIn("interior_previews", odata)

    def test_thunder_volt_hashes_unchanged(self):
        lock = ROOT / "COLORING_BOOK_THUNDER_VOLT_LOCKED_STATE.md"
        self.assertTrue(lock.is_file())
        text = lock.read_text(encoding="utf-8")
        self.assertIn("59c3d7cd0e22963cad995d762b4126f593ea97df2458577f80c431672aca4bac", text)
        self.assertIn("958c208e733d2ee8cf766bf2dd985ec6fdfcdd2ed5abe0122208463c8594273f", text)
        pkg = resolve_test_exports_root() / "a092b8e351174900a9082fbb46350364"
        pdf = pkg / "thunder_volt.pdf"
        zpath = pkg / "package.zip"
        if pdf.is_file():
            self.assertEqual(
                _sha256(pdf.read_bytes()),
                "59c3d7cd0e22963cad995d762b4126f593ea97df2458577f80c431672aca4bac",
            )
        if zpath.is_file():
            self.assertEqual(
                _sha256(zpath.read_bytes()),
                "958c208e733d2ee8cf766bf2dd985ec6fdfcdd2ed5abe0122208463c8594273f",
            )


if __name__ == "__main__":
    unittest.main()
