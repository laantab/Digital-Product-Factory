"""Planner cover photographs and the design rating.

Two things a customer relies on:

  * the Pexels picker never makes a live call in tests, fails closed with a
    readable message, only ever names files inside the Factory's own photo
    store, and keeps the chosen photograph on the project so a rebuild draws
    the same cover;
  * the Editor-in-Chief's design rating separates 7 (functional) from 8
    (professional), 9 (premium) and 10 (exceptional), and reserves 10 for a
    photographic cover with strong contrast.

Zero paid/external calls. Pexels HTTP is mocked at the transport layer, the
same way the ebook cover tests do it.
"""
from __future__ import annotations

import copy
import io
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("FACTORY_TEST_MODE", "1")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("TAVILY_API_KEY", "")
os.environ.setdefault("PEXELS_API_KEY", "")

import fitz  # noqa: E402
from PIL import Image  # noqa: E402

from app import app  # noqa: E402
from services.editor_in_chief import VERDICT_PASS  # noqa: E402
from services.editor_in_chief_planner import collect_planner_candidate, review_planner  # noqa: E402
from services.planner import THEMES, PlannerPdfRequest, build_planner_pdf  # noqa: E402
from services.planner import cover_photos as CP  # noqa: E402
from services.planner.design_rating import (  # noqa: E402
    collect_design_facts,
    contrast_ratio,
    rate_planner_design,
    tier_label,
)


def _jpeg_bytes(size=(1400, 2000), color=(96, 128, 168)) -> bytes:
    buf = io.BytesIO()
    im = Image.new("RGB", size, color)
    # A little structure so the photo does not look like a flat fill.
    px = im.load()
    for y in range(0, size[1], 40):
        for x in range(size[0]):
            px[x, y] = (color[0] + 40, color[1] + 30, color[2] + 20)
    im.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


MOCK_PHOTO = {
    "id": 4242, "width": 1400, "height": 2000,
    "photographer": "Test Photographer", "photographer_url": "https://www.pexels.com/@test",
    "url": "https://www.pexels.com/photo/4242/", "alt": "warm window light",
    "src": {"original": "https://images.pexels.com/photos/4242/original.jpeg",
            "large": "https://images.pexels.com/photos/4242/large.jpeg"},
}


def _mock_http(url, headers, *, binary=False):
    if binary:
        return _jpeg_bytes()
    if "/v1/photos/" in str(url):
        return dict(MOCK_PHOTO)
    return {"photos": [dict(MOCK_PHOTO)]}


def _allow_pexels():
    """Lift the test-mode block and install a fake key, for the mocked path only."""
    return (
        patch.dict(os.environ, {"FACTORY_TEST_MODE": "0", "PEXELS_API_KEY": "test-key-not-real"}),
        patch("services.ebook_pexels._http_get", side_effect=_mock_http),
    )


class QueryBuildingTests(unittest.TestCase):
    def test_the_search_phrase_comes_from_title_theme_and_context(self):
        q = CP.build_cover_query("Morning Light Faith Planner", "faith_planner", "warm_grace")
        self.assertIn("morning light", q)
        self.assertIn("devotional", q)
        self.assertIn(THEMES["warm_grace"].pexels_queries[0], q)
        self.assertNotIn("planner", q)

    def test_no_product_name_is_hard_coded(self):
        src = (ROOT / "services" / "planner" / "cover_photos.py").read_text(encoding="utf-8")
        self.assertNotIn("Family Faith", src)
        q = CP.build_cover_query("", "faith_planner", "joyful_light")
        self.assertTrue(q.startswith(THEMES["joyful_light"].pexels_queries[0]))

    def test_a_customer_phrase_wins_and_is_trimmed(self):
        q = CP.build_cover_query("Anything", "faith_planner", "warm_grace",
                                 user_query="  candle   on   a   table  ")
        self.assertEqual(q, "candle on a table")

    def test_suggestions_lead_with_the_built_phrase(self):
        sug = CP.suggested_queries("Quiet Mornings", "faith_planner", "floral_devotion")
        self.assertEqual(sug[0], CP.build_cover_query("Quiet Mornings", "faith_planner", "floral_devotion"))
        self.assertLessEqual(len(sug), 4)


class FailClosedTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_search_in_safe_mode_returns_a_message_and_no_photos(self):
        with patch("services.ebook_pexels._http_get", side_effect=AssertionError("live call")):
            found = CP.search_cover_photos(title="Grace", planner_type="faith_planner",
                                           design_theme="warm_grace")
        self.assertEqual(found["photos"], [])
        self.assertFalse(found["configured"])
        self.assertIn("painted a themed cover", found["message"])
        self.assertTrue(found["query"])

    def test_the_search_route_never_errors_and_never_leaks_originals(self):
        with patch("services.ebook_pexels._http_get", side_effect=AssertionError("live call")):
            resp = self.client.post("/planner/cover-photos", json={
                "title": "Grace", "planner_type": "faith_planner", "design_theme": "warm_grace"})
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertNotIn("_raw_photos", body)
        self.assertNotIn("original_url", resp.get_data(as_text=True))
        self.assertIn("message", body)

    def test_the_select_route_fails_closed_with_a_customer_message(self):
        with patch("services.ebook_pexels._http_get", side_effect=AssertionError("live call")):
            resp = self.client.post("/planner/cover-photo/select", json={"photo_id": "4242"})
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertFalse(body["ok"])
        self.assertTrue(body["message"])
        self.assertNotIn("Traceback", body["message"])

    def test_asset_ids_are_strictly_validated(self):
        for bad in ("", "../etc/passwd", "pexels-", "pexels-abc", "C:\\x.jpg", "pexels-1/../../x"):
            with self.subTest(asset=bad):
                self.assertEqual(CP.resolve_cover_asset(bad), "")

    def test_generate_with_the_factory_choice_falls_back_and_says_so(self):
        from services.product import generate_product

        tmp = tempfile.mkdtemp(prefix="planner_photo_")
        prev = os.environ.get("FLASK_EXPORTS_DIR")
        os.environ["FLASK_EXPORTS_DIR"] = tmp
        try:
            with patch("services.ebook_pexels._http_get", side_effect=AssertionError("live call")):
                out = generate_product("faith_planner", {
                    "pages": "24", "design_theme": "Warm Grace", "cover_image_choice": "factory"})
            self.assertEqual(out["layout_info"]["cover_image_source"], "procedural")
            self.assertTrue(any("painted a themed cover" in w for w in out["warnings"]))
            self.assertEqual(out["fields"]["cover_asset_id"], "")
            self.assertNotIn("cover_image_path", out["fields"])
        finally:
            if prev is None:
                os.environ.pop("FLASK_EXPORTS_DIR", None)
            else:
                os.environ["FLASK_EXPORTS_DIR"] = prev
            shutil.rmtree(tmp, ignore_errors=True)


class MockedPickerFlowTests(unittest.TestCase):
    """The whole customer flow against a mocked Pexels transport."""

    def setUp(self):
        self.client = app.test_client()
        self.tmp = tempfile.mkdtemp(prefix="planner_picker_")
        self._prev_dir = CP.PHOTO_DIR
        CP.PHOTO_DIR = os.path.join(self.tmp, "photos")
        self._prev_exports = os.environ.get("FLASK_EXPORTS_DIR")
        os.environ["FLASK_EXPORTS_DIR"] = self.tmp

    def tearDown(self):
        CP.PHOTO_DIR = self._prev_dir
        if self._prev_exports is None:
            os.environ.pop("FLASK_EXPORTS_DIR", None)
        else:
            os.environ["FLASK_EXPORTS_DIR"] = self._prev_exports
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_search_then_select_then_generate_uses_the_photograph(self):
        env, http = _allow_pexels()
        with env, http:
            resp = self.client.post("/planner/cover-photos", json={
                "title": "Quiet Mornings", "planner_type": "faith_planner",
                "design_theme": "warm_grace"})
            found = resp.get_json()
            self.assertTrue(found["configured"])
            self.assertEqual(len(found["photos"]), 1)
            self.assertEqual(found["photos"][0]["photo_id"], "4242")
            self.assertNotIn("original_url", resp.get_data(as_text=True))

            resp = self.client.post("/planner/cover-photo/select", json={"photo_id": "4242"})
            chosen = resp.get_json()
            self.assertTrue(chosen["ok"], chosen)
            self.assertEqual(chosen["asset_id"], "pexels-4242")
            self.assertIn("Test Photographer", chosen["attribution"])
            self.assertNotIn("path", chosen)
            self.assertTrue(os.path.isfile(CP.resolve_cover_asset("pexels-4242")))

        # Generation needs no network: the asset id resolves to the stored file.
        from services.product import generate_product

        with patch("services.ebook_pexels._http_get", side_effect=AssertionError("live call")):
            out = generate_product("faith_planner", {
                "pages": "24", "design_theme": "Warm Grace", "cover_style": "Full photo",
                "cover_image_choice": "pexels", "cover_asset_id": "pexels-4242",
                "planner_title": "Quiet Mornings"})
        self.assertEqual(out["layout_info"]["cover_image_source"], "file")
        self.assertEqual(out["fields"]["cover_asset_id"], "pexels-4242")
        self.assertEqual(out["warnings"], [])
        # The title is composed by the Factory, as real text over the photo.
        with fitz.open(out["pdf_path"]) as doc:
            self.assertIn("Quiet Mornings", doc[0].get_text())
            self.assertEqual(len(doc[0].get_images(full=True)), 1)

    def test_the_factory_choice_picks_and_records_a_photo_when_available(self):
        from services.product import generate_product

        env, http = _allow_pexels()
        with env, http:
            out = generate_product("faith_planner", {
                "pages": "24", "design_theme": "Joyful Light", "cover_image_choice": "factory"})
        self.assertEqual(out["layout_info"]["cover_image_source"], "file")
        self.assertEqual(out["fields"]["cover_asset_id"], "pexels-4242")
        self.assertIn("Test Photographer", out["fields"]["cover_photo_attribution"])

    def test_rebuild_from_the_saved_fields_is_deterministic_and_offline(self):
        env, http = _allow_pexels()
        with env, http:
            CP.select_cover_photo("4242")
        path = CP.resolve_cover_asset("pexels-4242")
        self.assertTrue(path)
        with patch("services.ebook_pexels._http_get", side_effect=AssertionError("live call")):
            a = build_planner_pdf(PlannerPdfRequest(planner_type="faith_planner", pages=12,
                                                    design_theme="warm_grace", cover_image_path=path,
                                                    package_id="rb_a"))
            b = build_planner_pdf(PlannerPdfRequest(planner_type="faith_planner", pages=12,
                                                    design_theme="warm_grace", cover_image_path=path,
                                                    package_id="rb_b"))
        self.assertEqual(a.layout_info["cover_image_source"], "file")
        with fitz.open(a.pdf_path) as da, fitz.open(b.pdf_path) as db:
            self.assertEqual(da[0].get_pixmap(dpi=30).samples, db[0].get_pixmap(dpi=30).samples)

    def test_a_tiny_photo_is_refused(self):
        env, _http = _allow_pexels()
        small = lambda url, headers, *, binary=False: (  # noqa: E731
            _jpeg_bytes(size=(300, 400)) if binary else _mock_http(url, headers))
        with env, patch("services.ebook_pexels._http_get", side_effect=small):
            with self.assertRaises(Exception):
                CP.select_cover_photo("4242")
        self.assertEqual(CP.resolve_cover_asset("pexels-4242"), "")


class DesignRatingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="planner_rating_")
        cls._prev = os.environ.get("FLASK_EXPORTS_DIR")
        os.environ["FLASK_EXPORTS_DIR"] = cls.tmp
        cls.reports = {}
        photo = os.path.join(cls.tmp, "hero.jpg")
        with open(photo, "wb") as fh:
            fh.write(_jpeg_bytes(size=(1800, 2600), color=(70, 40, 50)))
        for key, kw in (("painted", {}), ("photo", {"cover_image_path": photo, "cover_style": "full_photo"})):
            r = build_planner_pdf(PlannerPdfRequest(
                planner_type="faith_planner", pages=24, design_theme="warm_grace",
                title="Quiet Mornings", author="Digital Product Factory",
                package_id=f"rating_{key}", **kw))
            images = []
            with fitz.open(r.pdf_path) as doc:
                for i, page in enumerate(doc):
                    p = os.path.join(cls.tmp, f"{key}_{i + 1:03d}.png")
                    page.get_pixmap(dpi=72).save(p)
                    images.append(p)
            cand = collect_planner_candidate(r.plan, pdf_path=r.pdf_path, package_dir=r.package_dir,
                                             page_images=images, author="Digital Product Factory",
                                             layout_info=r.layout_info)
            cls.reports[key] = (r, cand, review_planner(cand))

    @classmethod
    def tearDownClass(cls):
        if cls._prev is None:
            os.environ.pop("FLASK_EXPORTS_DIR", None)
        else:
            os.environ["FLASK_EXPORTS_DIR"] = cls._prev
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_tiers_are_named(self):
        self.assertEqual(tier_label(10), "exceptional")
        self.assertEqual(tier_label(9), "premium")
        self.assertEqual(tier_label(8), "professional")
        self.assertEqual(tier_label(7), "functional")

    def test_a_painted_cover_cannot_reach_ten(self):
        _r, _c, rep = self.reports["painted"]
        self.assertEqual(rep.verdict, VERDICT_PASS, [f.code for f in rep.findings])
        self.assertLessEqual(rep.evidence["design_rating"], 9)
        self.assertIn("DESIGN_COVER_NO_PHOTOGRAPH", rep.evidence["design_deductions"][0])
        self.assertLess(rep.overall, 10.0)
        self.assertGreaterEqual(rep.overall, 9.0)

    def test_a_good_photograph_cover_can_reach_ten(self):
        _r, _c, rep = self.reports["photo"]
        self.assertEqual(rep.verdict, VERDICT_PASS, [f.code for f in rep.findings])
        self.assertEqual(rep.evidence["design_cover_score"], 10,
                         rep.evidence["design_deductions"])

    def test_only_design_minors_separate_the_two(self):
        for key in ("painted", "photo"):
            _r, _c, rep = self.reports[key]
            for fi in rep.findings:
                self.assertTrue(fi.code.startswith("DESIGN_"), fi.code)
                self.assertEqual(fi.severity, "minor")

    def test_weak_contrast_flat_hierarchy_and_bare_forms_lose_points(self):
        r, cand, _rep = self.reports["painted"]
        facts = collect_design_facts(r.pdf_path)
        # Sabotage the facts the way a weak design would present them.
        bad = copy.deepcopy(facts)
        bad["cover"]["title_size"] = 14.0
        bad["cover"]["sizes"] = [14.0, 13.0]
        bad["cover"]["fonts"] = ["OneFace"]
        for pg in bad["pages"][1:]:
            pg["curves"] = 0
            pg["rule_pitch"] = 11.0
            for sp in pg["spans"]:
                sp["font"] = "OneFace"
                sp["size"] = 9.0
                sp["color"] = 0xBBBBBB
        from services.editor_in_chief import analyse_rendered_pages
        from services.editor_in_chief_planner import analyse_planner_design

        stats = analyse_rendered_pages(cand["page_images"])["pages"]
        rating = rate_planner_design(
            bad, page_kinds=cand["page_kinds"], page_images=cand["page_images"],
            page_stats=stats, design_stats=analyse_planner_design(cand["page_images"]),
            theme=THEMES["warm_grace"], cover_source="procedural", cover_dpi=200.0)
        codes = {code for _c, code, _r in rating["deductions"]}
        for expected in ("DESIGN_COVER_TITLE_SMALL", "DESIGN_COVER_FLAT_HIERARCHY",
                         "DESIGN_COVER_ONE_FACE", "DESIGN_TYPOGRAPHY_FLAT",
                         "DESIGN_WEAK_CONTRAST", "DESIGN_WRITING_LINES_TIGHT",
                         "DESIGN_GENERIC_WORKSHEET"):
            self.assertIn(expected, codes)
        self.assertLessEqual(rating["interior"], 7)
        self.assertEqual(rating["tier"], tier_label(rating["rating"]))

    def test_contrast_ratio_is_wcag_shaped(self):
        self.assertAlmostEqual(contrast_ratio((0, 0, 0), (255, 255, 255)), 21.0, places=1)
        self.assertLess(contrast_ratio((200, 200, 200), (255, 255, 255)), 2.0)


if __name__ == "__main__":
    unittest.main()
