"""Universal editorial search-planning correction. Zero paid/external calls
(Pexels HTTP is mocked where a live-shaped call is needed).

Proves:
  1. Book-level equipment survives every chapter query.
  2. Audience context is preserved appropriately.
  3. Filler words ("without guessing", "turning power into", ...) are excluded.
  4. "Deadlift" in a kettlebell book cannot silently become a barbell search.
  5. Candidate sets are ranked rather than first-result accepted (cover retry
     tries the next candidate when the top-ranked one's layout fails).
  6. Wrong-equipment candidates are rejected.
  7. Exact-action candidates outrank generic fitness images.
  8. Long product descriptions do not become cover titles.
  9. Stored researched titles / manuscript H1 titles are preserved.
  10. Business, gardening, cooking, technical, and reflective books derive
      different search briefs.
  11. No project-specific string, ID, image URL, or asset hash is hardcoded
      anywhere in the production code under test (structural check).
"""
from __future__ import annotations

import os
import re
import sys
import unittest
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

from services.ebook_pexels import chapter_pexels_queries  # noqa: E402
from services.ebook_visual_brief_common import (  # noqa: E402
    detect_audience_terms,
    detect_equipment_terms,
    resolve_cover_identity,
    strip_filler,
)
from services.ebook_visual_match import build_visual_brief, score_cover_photo, score_photo_against_brief  # noqa: E402

# A generic kettlebell-book fixture used across several tests. Not project
# #21243's real title/topic strings -- reworded so no test in this file
# reuses its exact production text.
_KB_TITLE = "Strength Basics With a Single Weight"
_KB_TOPIC = "A kettlebell training guide for older beginners covering six core lifts"
_KB_CHAPTER = "The Deadlift: Learning to Hinge Without Guessing"


class TestUniversalVisualSearchPlanning(unittest.TestCase):
    def test_01_book_level_equipment_survives_every_chapter_query(self):
        chapters = [
            "The Deadlift: Learning to Hinge Without Guessing",
            "The Kettlebell Swing: Turning Power Into a Controlled Hinge",
            "The Goblet Squat: Building Depth, Balance, and Bracing",
            "The Press: Training Overhead Strength With Better Positioning",
            "The Row: Using the Upper Back Instead of Yanking the Bell",
            "The Carry: Turning Technique Into Everyday Strength",
        ]
        for chapter in chapters:
            queries = chapter_pexels_queries(chapter=chapter, title=_KB_TITLE, topic=_KB_TOPIC)
            self.assertTrue(
                any("kettlebell" in q.lower() for q in queries[:2]),
                f"no kettlebell in top queries for {chapter!r}: {queries}",
            )

    def test_02_audience_context_preserved(self):
        terms = detect_audience_terms("adults over 50", _KB_TOPIC)
        self.assertIn("adults over 50", terms)
        queries = chapter_pexels_queries(chapter=_KB_CHAPTER, title=_KB_TITLE, topic=_KB_TOPIC, audience="adults over 50")
        self.assertTrue(any("50" in q for q in queries))

    def test_03_filler_words_excluded(self):
        cleaned = strip_filler(_KB_CHAPTER)
        self.assertNotIn("without", cleaned.lower())
        self.assertNotIn("guessing", cleaned.lower())
        cleaned2 = strip_filler("The Kettlebell Swing: Turning Power Into a Controlled Hinge")
        self.assertNotIn("turning", cleaned2.lower())

    def test_04_deadlift_cannot_silently_become_barbell_search(self):
        aid = {"type": "stock photo", "title": "Deadlift", "caption": "Deadlift", "chapter": _KB_CHAPTER, "chapter_index": 0}
        brief = build_visual_brief(aid, chapter=_KB_CHAPTER, title=_KB_TITLE, topic=_KB_TOPIC)
        self.assertIn("barbell", brief.forbidden_tokens)
        report = score_photo_against_brief(
            brief,
            page_url="https://example.com/photo/man-holding-a-barbell-000",
            filename="000",
        )
        self.assertEqual(report.status, "reject")
        self.assertIn("barbell", report.rejection_reason)

    def test_05_cover_retry_tries_next_candidate_when_top_layout_fails(self):
        from services.ebook_customer_path import complete_photo_cover

        candidates = [
            {"photo_id": "p1", "width": 1600, "height": 2400, "alt": "kettlebell training", "page_url": "https://example.com/p1"},
            {"photo_id": "p2", "width": 1600, "height": 2400, "alt": "kettlebell training", "page_url": "https://example.com/p2"},
        ]
        attempts: list[str] = []

        def fake_search(query, **kwargs):
            return {"photos": candidates}

        def fake_download(photo):
            from PIL import Image
            import io

            buf = io.BytesIO()
            Image.new("RGB", (1600, 2400), (60, 90, 60)).save(buf, format="JPEG", quality=85)
            return buf.getvalue()

        def fake_first_passing_layout(cover):
            pid = ((cover or {}).get("source") or {}).get("pexels", {}).get("photo_id", "")
            attempts.append(pid)
            return "layout-a" if pid == "p2" else ""

        def fake_store_source_bytes(payload, raw, **kwargs):
            return {"sha256": "fake-sha", "pexels": {}}

        def fake_activate_source(payload, source, **kwargs):
            out = dict(payload)
            out["cover_design"] = {**out.get("cover_design", {}), "source": source}
            return out

        with patch("services.ebook_customer_path.fixture_mode", return_value=False), \
             patch("services.ebook_customer_path.search_pexels", side_effect=fake_search), \
             patch("services.ebook_customer_path.download_pexels_original", side_effect=fake_download), \
             patch("services.ebook_customer_path._store_source_bytes", side_effect=fake_store_source_bytes), \
             patch("services.ebook_customer_path._activate_source", side_effect=fake_activate_source), \
             patch("services.ebook_customer_path._first_passing_layout", side_effect=fake_first_passing_layout), \
             patch("services.ebook_customer_path.select_layout", side_effect=lambda payload, layout, **k: {**payload, "cover_design": {**payload.get("cover_design", {}), "selected_layout": layout}}), \
             patch("services.ebook_visual_match.score_cover_photo", return_value=0.8):
            result = complete_photo_cover(
                {}, title=_KB_TITLE, subtitle="A Practical Guide", author="Test Author",
                fields={"topic": _KB_TOPIC}, package_id="unit-test-cover-pkg",
            )
        # Both candidates were tried in order (not just the first).
        self.assertEqual(attempts, ["p1", "p2"])
        self.assertEqual(result.get("cover_design", {}).get("selected_layout"), "layout-a")

    def test_06_wrong_equipment_candidate_rejected_by_cover_scorer(self):
        score_wrong = score_cover_photo(
            {"width": 1600, "height": 2400, "alt": "man with a barbell in a gym", "page_url": "https://example.com/x"},
            title=_KB_TITLE, topic=_KB_TOPIC,
        )
        self.assertEqual(score_wrong, 0.0)

    def test_07_exact_action_outranks_generic_fitness_image(self):
        score_generic = score_cover_photo(
            {"width": 1600, "height": 2400, "alt": "", "page_url": "https://example.com/generic"},
            title=_KB_TITLE, topic=_KB_TOPIC,
        )
        score_specific = score_cover_photo(
            {"width": 1600, "height": 2400, "alt": "kettlebell training session", "page_url": "https://example.com/specific"},
            title=_KB_TITLE, topic=_KB_TOPIC,
        )
        self.assertGreater(score_specific, score_generic)

    def test_08_long_product_description_does_not_become_cover_title(self):
        long_desc = (
            "A form-focused strength ebook teaching the six foundational movements "
            "for older beginners with regressions, common mistakes, and confidence-building drills"
        )
        content_md = (
            "# Strength Basics With a Single Weight: A Practical Guide to Six Core Lifts\n\n"
            "*By Test Author*\n\nBody text follows.\n"
        )
        identity = resolve_cover_identity(
            stored_title=long_desc, stored_subtitle="", stored_author="", topic=long_desc, content_md=content_md,
        )
        self.assertNotEqual(identity["title"], long_desc)
        self.assertLessEqual(len(identity["title"].split()), 12)
        self.assertEqual(identity["title"], "Strength Basics With a Single Weight")
        self.assertEqual(identity["subtitle"], "A Practical Guide to Six Core Lifts")
        self.assertEqual(identity["author"], "Test Author")

    def test_09_stored_short_title_is_preserved_not_overwritten(self):
        content_md = "# Some Other H1 That Should Be Ignored\n\nBody.\n"
        identity = resolve_cover_identity(
            stored_title="A Deliberately Chosen Short Title",
            stored_subtitle="Existing Subtitle",
            stored_author="Existing Author",
            topic="some topic sentence",
            content_md=content_md,
        )
        self.assertEqual(identity["title"], "A Deliberately Chosen Short Title")
        self.assertEqual(identity["subtitle"], "Existing Subtitle")
        self.assertEqual(identity["author"], "Existing Author")

    def test_10_different_book_types_derive_different_briefs(self):
        cases = {
            "business": ("Pricing Your Freelance Services", "freelance business pricing systems", "Pricing Comparison: Hourly vs Flat Rate"),
            "gardening": ("Container Gardening Basics", "container gardening for small spaces", "Choosing the Right Pots and Soil"),
            "cooking": ("Sourdough at Home", "sourdough baking for beginners", "Shaping and Scoring Your Loaf"),
            "technical": ("Spreadsheet Automation", "excel workflow automation for small teams", "Building Your First Macro"),
            "reflective": ("Finding Stillness", "a reflective memoir on grief and renewal", "The Weight of Quiet Rooms"),
        }
        equipment_by_case = {}
        for name, (title, topic, chapter) in cases.items():
            aid = {"type": "stock photo", "title": chapter, "caption": chapter, "chapter": chapter, "chapter_index": 0}
            brief = build_visual_brief(aid, chapter=chapter, title=title, topic=topic)
            equipment_by_case[name] = detect_equipment_terms(title, topic, chapter)
            # None of these non-equipment topics should fabricate a required
            # named implement out of nowhere.
            self.assertEqual(equipment_by_case[name], [])
        # Business and gardening chapters at minimum should not collapse to
        # an identical generic brief -- they differ in subject/action tokens.
        biz_aid = {"type": "table", "title": cases["business"][2], "chapter": cases["business"][2]}
        biz_brief = build_visual_brief(biz_aid, chapter=cases["business"][2], title=cases["business"][0], topic=cases["business"][1])
        garden_brief = build_visual_brief(
            {"type": "stock photo", "title": cases["gardening"][2], "chapter": cases["gardening"][2]},
            chapter=cases["gardening"][2], title=cases["gardening"][0], topic=cases["gardening"][1],
        )
        self.assertNotEqual(sorted(biz_brief.subject_tokens), sorted(garden_brief.subject_tokens))

    def test_11_no_project_specific_hardcoding_in_source(self):
        # Structural guard: the production files touched by this pass must
        # never reference project #21243's id, its exact stored strings, or
        # any Pexels photo id/URL captured during the earlier acquisition run.
        forbidden = ("21243", "4720792", "ef919a9f9aca494f8efa3759428e48a9")
        files = [
            ROOT / "services" / "ebook_visual_brief_common.py",
            ROOT / "services" / "ebook_pexels.py",
            ROOT / "services" / "ebook_visual_match.py",
            ROOT / "services" / "ebook_customer_path.py",
        ]
        for path in files:
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(token, text, f"{token!r} hardcoded in {path.name}")


if __name__ == "__main__":
    unittest.main()
