"""KDP Implementation Pass 1: authoritative foundations (deterministic, zero paid calls).

Covers print profile, geometry (trim/bleed/margin/gutter/page/cover/spine),
ISBN/metadata validation, activity vs low-content classification, and AI
disclosure records. Does not wire preflight UI or export blocking.
"""
from __future__ import annotations

import os
import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

os.environ["FACTORY_TEST_MODE"] = "1"
os.environ["OPENAI_API_KEY"] = ""
os.environ["TAVILY_API_KEY"] = ""
os.environ["AI_INTEGRATIONS_OPENAI_API_KEY"] = ""

from services.kdp import (  # noqa: E402
    AiProvenance,
    BleedMode,
    ContentClass,
    GeometryError,
    IsbnOption,
    PrintProfileError,
    SOURCE_INDEX,
    build_ai_disclosure,
    build_print_profile,
    calculate_spine,
    classify_content,
    cover_size,
    geometry_bundle,
    gutter_margin_in,
    interior_page_size,
    isbn13_check_digit,
    margin_requirements,
    normalize_isbn,
    validate_book_metadata,
    validate_isbn,
)

# Well-known valid ISBN-13 (ISO 2108 example family): 978-0-306-40615-7
VALID_ISBN13 = "9780306406157"


class TestPrintProfile(unittest.TestCase):
    def test_build_common_paperback_profile(self):
        profile = build_print_profile(
            {
                "binding": "paperback",
                "ink": "black",
                "paper": "white",
                "trim_width_in": "6",
                "trim_height_in": "9",
                "has_bleed": True,
                "page_count": 100,
            }
        )
        self.assertEqual(profile.trim.key, "6x9")
        self.assertEqual(profile.bleed, BleedMode.WITH_BLEED)
        self.assertEqual(profile.page_count, 100)

    def test_reject_unknown_trim(self):
        with self.assertRaises(PrintProfileError):
            build_print_profile(
                {
                    "ink": "black",
                    "paper": "white",
                    "trim_width_in": "3",
                    "trim_height_in": "3",
                    "has_bleed": False,
                    "page_count": 50,
                }
            )

    def test_reject_page_count_out_of_range(self):
        with self.assertRaises(PrintProfileError):
            build_print_profile(
                {
                    "ink": "black",
                    "paper": "white",
                    "trim_width_in": "6",
                    "trim_height_in": "9",
                    "has_bleed": False,
                    "page_count": 20,
                }
            )

    def test_standard_color_min_72(self):
        with self.assertRaises(PrintProfileError):
            build_print_profile(
                {
                    "ink": "standard_color",
                    "paper": "white",
                    "trim_width_in": "6",
                    "trim_height_in": "9",
                    "has_bleed": True,
                    "page_count": 50,
                }
            )
        profile = build_print_profile(
            {
                "ink": "standard_color",
                "paper": "white",
                "trim_width_in": "6",
                "trim_height_in": "9",
                "has_bleed": True,
                "page_count": 72,
            }
        )
        self.assertEqual(profile.page_count, 72)

    def test_color_ink_requires_white_paper(self):
        with self.assertRaises(PrintProfileError):
            build_print_profile(
                {
                    "ink": "premium_color",
                    "paper": "cream",
                    "trim_width_in": "6",
                    "trim_height_in": "9",
                    "has_bleed": True,
                    "page_count": 100,
                }
            )

    def test_hardcover_unavailable_groundwood(self):
        with self.assertRaises(PrintProfileError):
            build_print_profile(
                {
                    "binding": "hardcover",
                    "ink": "black",
                    "paper": "groundwood",
                    "trim_width_in": "6",
                    "trim_height_in": "9",
                    "has_bleed": False,
                    "page_count": 100,
                }
            )


class TestGeometry(unittest.TestCase):
    def _profile(self, **overrides):
        data = {
            "ink": "black",
            "paper": "white",
            "trim_width_in": "6",
            "trim_height_in": "9",
            "has_bleed": True,
            "page_count": 100,
        }
        data.update(overrides)
        return build_print_profile(data)

    def test_bleed_page_size_6x9(self):
        # GVBQ3CMEQW3W2VL6 example: 6x9 → 6.125 x 9.25 with bleed
        page = interior_page_size(self._profile(has_bleed=True))
        self.assertEqual(page.width_in, Decimal("6.125000"))
        self.assertEqual(page.height_in, Decimal("9.250000"))

    def test_no_bleed_page_size_equals_trim(self):
        page = interior_page_size(self._profile(has_bleed=False))
        self.assertEqual(page.width_in, Decimal("6"))
        self.assertEqual(page.height_in, Decimal("9"))

    def test_gutter_tiers(self):
        self.assertEqual(gutter_margin_in(24), Decimal("0.375"))
        self.assertEqual(gutter_margin_in(150), Decimal("0.375"))
        self.assertEqual(gutter_margin_in(151), Decimal("0.5"))
        self.assertEqual(gutter_margin_in(300), Decimal("0.5"))
        self.assertEqual(gutter_margin_in(301), Decimal("0.625"))
        self.assertEqual(gutter_margin_in(501), Decimal("0.75"))
        self.assertEqual(gutter_margin_in(701), Decimal("0.875"))
        with self.assertRaises(GeometryError):
            gutter_margin_in(23)

    def test_outside_margins_depend_on_bleed(self):
        with_bleed = margin_requirements(self._profile(has_bleed=True))
        no_bleed = margin_requirements(self._profile(has_bleed=False))
        self.assertEqual(with_bleed.outside_in, Decimal("0.375"))
        self.assertEqual(no_bleed.outside_in, Decimal("0.25"))
        self.assertEqual(with_bleed.inside_gutter_in, Decimal("0.375"))

    def test_spine_white_paper_coefficient(self):
        # G201953020: white paper page_count × 0.002252
        spine = calculate_spine(self._profile(page_count=100, paper="white"))
        self.assertEqual(spine.status, "ok")
        self.assertEqual(spine.width_in, Decimal("0.225200"))
        self.assertEqual(spine.coefficient_in_per_page, Decimal("0.002252"))
        self.assertTrue(spine.spine_text_allowed)

    def test_spine_cream_and_color_coefficients(self):
        cream = calculate_spine(self._profile(page_count=200, paper="cream"))
        self.assertEqual(cream.width_in, Decimal("0.500000"))
        self.assertEqual(cream.coefficient_in_per_page, Decimal("0.0025"))

        ground = calculate_spine(
            self._profile(page_count=100, paper="groundwood")
        )
        self.assertEqual(ground.coefficient_in_per_page, Decimal("0.00235"))

        std = calculate_spine(
            self._profile(
                ink="standard_color",
                paper="white",
                page_count=100,
            )
        )
        self.assertEqual(std.coefficient_in_per_page, Decimal("0.002252"))

        prem = calculate_spine(
            self._profile(
                ink="premium_color",
                paper="white",
                page_count=100,
            )
        )
        self.assertEqual(prem.coefficient_in_per_page, Decimal("0.002347"))
        self.assertEqual(prem.width_in, Decimal("0.234700"))

    def test_spine_text_min_pages(self):
        low = calculate_spine(self._profile(page_count=78))
        self.assertFalse(low.spine_text_allowed)
        ok = calculate_spine(self._profile(page_count=79))
        self.assertTrue(ok.spine_text_allowed)

    def test_cover_size_formula(self):
        # Cover W = 0.125 + 6 + spine + 6 + 0.125; H = 0.125 + 9 + 0.125
        profile = self._profile(page_count=100, paper="white")
        spine = calculate_spine(profile)
        cover = cover_size(profile, spine)
        expected_w = Decimal("0.125") + Decimal("6") + spine.width_in + Decimal("6") + Decimal(
            "0.125"
        )
        self.assertEqual(cover.width_in, expected_w.quantize(Decimal("0.000001")))
        self.assertEqual(cover.height_in, Decimal("9.250000"))

    def test_geometry_bundle_deterministic(self):
        a = geometry_bundle(self._profile())
        b = geometry_bundle(self._profile())
        self.assertEqual(a, b)
        self.assertIn("kdp.amazon.com", a["constants"]["sources"]["trim_bleed_margins"])


class TestIsbnAndMetadata(unittest.TestCase):
    def test_isbn13_check_digit(self):
        self.assertEqual(isbn13_check_digit("978030640615"), "7")
        self.assertEqual(normalize_isbn("978-0-306-40615-7"), VALID_ISBN13)

    def test_reject_bad_check_digit(self):
        result = validate_isbn(isbn="9780306406150", option=IsbnOption.OWN)
        self.assertFalse(result.ok)
        self.assertTrue(any("check digit" in e.lower() for e in result.errors))

    def test_never_invent_isbn(self):
        result = validate_isbn(option=IsbnOption.OWN)
        self.assertFalse(result.ok)
        self.assertTrue(any("caller-supplied" in e for e in result.errors))
        with self.assertRaises(Exception):
            normalize_isbn("generate")

    def test_low_content_ineligible_for_free_kdp_isbn(self):
        result = validate_isbn(
            option=IsbnOption.KDP_FREE,
            content_class=ContentClass.LOW_CONTENT,
        )
        self.assertFalse(result.ok)

    def test_publish_without_only_for_low_content(self):
        bad = validate_isbn(
            option=IsbnOption.PUBLISH_WITHOUT,
            content_class=ContentClass.ACTIVITY,
        )
        self.assertFalse(bad.ok)
        good = validate_isbn(
            option=IsbnOption.PUBLISH_WITHOUT,
            content_class=ContentClass.LOW_CONTENT,
        )
        self.assertTrue(good.ok)

    def test_validate_book_metadata_ok(self):
        result = validate_book_metadata(
            {
                "title": "Sample Activity Book",
                "author": "Test Author",
                "description": "A puzzle book.",
                "product_type": "word_search",
                "isbn_option": "own",
                "isbn": VALID_ISBN13,
                "imprint": "Example Press",
            }
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.content_class, ContentClass.ACTIVITY.value)
        self.assertEqual(result.isbn.normalized, VALID_ISBN13)


class TestClassification(unittest.TestCase):
    def test_factory_activity_products(self):
        for pt in (
            "coloring_book",
            "word_search",
            "crossword",
            "math_worksheet",
            "spelling_worksheet",
        ):
            result = classify_content(product_type=pt)
            self.assertEqual(result.content_class, ContentClass.ACTIVITY)
            self.assertFalse(result.low_content_checkbox_required)
            self.assertTrue(result.free_kdp_isbn_eligible)

    def test_ebook_standard(self):
        result = classify_content(product_type="ebook")
        self.assertEqual(result.content_class, ContentClass.STANDARD)

    def test_explicit_low_content(self):
        result = classify_content(explicit_class="notebook")
        self.assertEqual(result.content_class, ContentClass.LOW_CONTENT)
        self.assertTrue(result.low_content_checkbox_required)
        self.assertFalse(result.free_kdp_isbn_eligible)

    def test_unknown_not_forced_low_content(self):
        result = classify_content(product_type="mystery_future_product")
        self.assertEqual(result.content_class, ContentClass.UNKNOWN)


class TestAiDisclosure(unittest.TestCase):
    def test_missing_defaults_to_unknown_not_none(self):
        record = build_ai_disclosure({})
        self.assertEqual(record.text, AiProvenance.UNKNOWN)
        self.assertEqual(record.images, AiProvenance.UNKNOWN)
        self.assertEqual(record.translations, AiProvenance.UNKNOWN)
        self.assertTrue(record.has_unknown_provenance)
        self.assertFalse(record.requires_kdp_ai_generated_disclosure)

    def test_unknown_blocks_assert_no_ai(self):
        record = build_ai_disclosure({"assert_no_ai": True})
        self.assertFalse(record.ok)
        self.assertTrue(any("unknown" in e.lower() for e in record.errors))

    def test_ai_generated_requires_disclosure(self):
        record = build_ai_disclosure(
            {
                "text": "none",
                "images": "ai_generated",
                "translations": "none",
            }
        )
        self.assertTrue(record.ok)
        self.assertTrue(record.requires_kdp_ai_generated_disclosure)

    def test_ai_assisted_does_not_require_disclosure(self):
        record = build_ai_disclosure(
            {
                "text": "ai_assisted",
                "images": "none",
                "translations": "none",
            }
        )
        self.assertTrue(record.ok)
        self.assertFalse(record.requires_kdp_ai_generated_disclosure)

    def test_assert_no_ai_only_when_all_none(self):
        record = build_ai_disclosure(
            {
                "text": "none",
                "images": "none",
                "translations": "none",
                "assert_no_ai": True,
            }
        )
        self.assertTrue(record.ok)
        self.assertTrue(record.assert_no_ai)

    def test_asset_unknown_not_collapsed_to_none(self):
        record = build_ai_disclosure(
            {
                "text": "none",
                "images": "none",
                "translations": "none",
                "assets": [{"kind": "images", "provenance": "unknown"}],
            }
        )
        self.assertEqual(record.images, AiProvenance.UNKNOWN)
        self.assertTrue(record.has_unknown_provenance)


class TestSourcesWired(unittest.TestCase):
    def test_source_index_has_amazon_urls(self):
        self.assertIn("trim_bleed_margins", SOURCE_INDEX)
        self.assertTrue(SOURCE_INDEX["paperback_cover"].startswith("https://kdp.amazon.com/"))
        self.assertTrue(SOURCE_INDEX["ai_disclosure"].startswith("https://kdp.amazon.com/"))


if __name__ == "__main__":
    unittest.main()
