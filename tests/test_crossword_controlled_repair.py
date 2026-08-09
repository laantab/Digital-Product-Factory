"""Focused regression checks for the controlled crossword repair.

These tests encode the acceptance gate. They must fail before the repair
where the defect exists, and pass after. Do not weaken requirements to
make a test pass.
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import sys
import unittest
import unittest.mock
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.crossword.crossword_fallback import (
    EVERYDAY_LIFE,
    GOLD_RUSH,
    _normalize_theme,
    get_fallback_words_and_clues,
)
from services.crossword.word_entries import suggest_crossword_words_from_topic
from services.crossword.book import build_crossword_puzzles
from services.crossword.direct_pdf_renderer import build_crossword_book_pdf_bytes
from services.factory.puzzle_plan import DEFAULT_BOOK_COUNTS, parse_puzzle_output_plan
from services.product import _crossword_plan, _resolve_crossword_words


_FORBIDDEN_ANSWERS = {
    "KITCHEN", "PILLOW", "CURTAIN", "BEDROOM", "BATHROOM", "BACKYARD",
    "GARAGE", "BREAKFAST", "COFFEE", "LUNCH", "DINNER", "SALAD", "PASTA",
    "RABBIT", "GIRAFFE", "PANDA", "PENGUIN", "SKIRT", "DRESS", "SOCKS",
    "MONTHS", "OCTOBER", "FAMILY", "GRANDMA", "GRANDPA", "MOTHER", "FATHER",
}
_GENERIC_CLUE_SNIPPETS = (
    "related to the theme",
    "related to california",
    "related to daily",
    "crossword word",
    "common word",
    "mystery word",
    "everyday item",
)
_GOLD_RUSH_ANSWERS = {
    re.sub(r"[^A-Za-z]", "", w).upper() for w, _ in GOLD_RUSH
}
# Everyday-life answers that are NOT also Gold Rush vocabulary.
_EVERYDAY_SAMPLE = {
    re.sub(r"[^A-Za-z]", "", w).upper()
    for w, _ in EVERYDAY_LIFE
} - _GOLD_RUSH_ANSWERS


class TestGoldRushTopicRouting(unittest.TestCase):
    def test_california_gold_rush_days_maps_to_gold_rush(self):
        self.assertEqual(_normalize_theme("California Gold Rush Days"), "gold_rush")

    def test_california_goal_rush_days_maps_to_gold_rush(self):
        self.assertEqual(_normalize_theme("California Goal Rush Days"), "gold_rush")

    def test_goal_rush_title_normalized_to_gold_rush(self):
        plan = _crossword_plan({
            "book_title": "California Goal Rush Days",
            "theme": "California Goal Rush Days",
            "output_format": "Full Book",
            "puzzles": "12",
            "creation_mode": "Topic (AI generates words)",
            "difficulty": "Easy",
            "include_answer_key": "Yes",
        })
        self.assertEqual(plan["title"], "California Gold Rush Days")
        self.assertIn("Gold Rush", plan["sub_topic"])
        self.assertNotIn("Goal Rush", plan["title"])


class TestNoSilentEverydayFallback(unittest.TestCase):
    def test_specific_unmatched_topic_does_not_receive_everyday_life(self):
        theme = "Purple Quantum Nebula Widgets"
        self.assertNotEqual(_normalize_theme(theme), "everyday_life")
        words, clues = get_fallback_words_and_clues(theme, count=20)
        self.assertEqual(words, [])
        self.assertEqual(clues, {})

        suggested, warnings, errors = suggest_crossword_words_from_topic(theme, max_words=40)
        self.assertFalse(suggested, f"Expected empty suggestion, got {suggested[:10]}")
        self.assertTrue(errors)
        joined = " ".join(errors).lower()
        self.assertTrue(
            "topic-relevant" in joined or "custom word list" in joined or "could not" in joined,
            f"Expected clear fail-closed error, got: {errors}",
        )


class TestTopicModeAuthoritativePool(unittest.TestCase):
    def test_topic_mode_uses_supplied_resolved_pool(self):
        pool = "\n".join([
            "GOLD", "NUGGET", "PROSPECTOR", "PANNING", "SLUICE",
            "PICKAXE", "SHOVEL", "CLAIM", "PLACER", "MINER",
            "COLOMA", "SUTTER", "MARSHALL", "SIERRA", "BOOMTOWN",
            "ORE", "MINE", "CAMP", "RIVER", "QUARTZ",
        ])
        with unittest.mock.patch(
            "services.crossword.book.suggest_crossword_words_from_topic"
        ) as mocked:
            mocked.side_effect = AssertionError(
                "book.py must not re-suggest vocabulary when an authoritative pool is supplied"
            )
            puzzles, warnings, errors = build_crossword_puzzles(
                mode="topic",
                product_title="California Gold Rush Days",
                custom_words=pool,
                theme="California Gold Rush Days",
                difficulty="easy",
                grid_size=15,
                number_of_puzzles=2,
                words_per_puzzle=8,
                output_type="book",
                use_ai_words=False,
            )
        self.assertGreaterEqual(len(puzzles), 1)
        placed = {w.upper() for p in puzzles for w in p.placed_words}
        self.assertTrue(placed & {"GOLD", "NUGGET", "PROSPECTOR", "PANNING", "SLUICE"})

    def test_old_stored_custom_words_do_not_override_topic_mode(self):
        fields = {
            "book_title": "California Gold Rush Days",
            "theme": "California Gold Rush Days",
            "output_format": "Full Book",
            "puzzles": "12",
            "creation_mode": "Topic (AI generates words)",
            "difficulty": "Easy",
            "custom_words": "KITCHEN\nBEDROOM\nBREAKFAST\nGRANDMA",
        }
        plan = _crossword_plan(fields)
        resolved = _resolve_crossword_words(
            fields,
            plan,
            stored_words="KITCHEN\nBEDROOM\nBREAKFAST\nGRANDMA",
        )
        resolved_upper = {w.strip().upper() for w in resolved.splitlines() if w.strip()}
        self.assertFalse(resolved_upper & _FORBIDDEN_ANSWERS)
        self.assertTrue(resolved_upper & {"GOLD", "NUGGET", "PROSPECTOR", "MINER", "CLAIM"})


class TestFullBookDefaultsAndPageCount(unittest.TestCase):
    def test_full_book_defaults_to_12_puzzles(self):
        self.assertEqual(DEFAULT_BOOK_COUNTS.get("crossword"), 12)
        plan = parse_puzzle_output_plan(
            {"output_format": "Full Book"},
            product_type="crossword",
        )
        self.assertEqual(plan["page_count"], 12)
        cw = _crossword_plan({
            "book_title": "California Gold Rush Days",
            "theme": "California Gold Rush Days",
            "output_format": "Full Book",
            "creation_mode": "Topic (AI generates words)",
            "difficulty": "Easy",
            "include_answer_key": "Yes",
        })
        self.assertEqual(cw["worksheets"], 12)

    def test_full_book_ignores_legacy_ten_puzzle_submission(self):
        """Browser autofill / legacy UI sent puzzles=10; Full Book must still be 12."""
        cw = _crossword_plan({
            "book_title": "California Gold Rush Days",
            "theme": "California Gold Rush Days",
            "output_format": "Full Book",
            "puzzles": "10",
            "creation_mode": "Topic (AI generates words)",
            "difficulty": "Easy",
            "include_answer_key": "Yes",
            "include_cover": "Yes",
        })
        self.assertEqual(cw["worksheets"], 12)
        self.assertEqual(cw["output_type"], "book")

    def test_normalize_rewrites_legacy_ten_puzzle_saved_fields(self):
        from services.product import normalize_crossword_project_data

        data = normalize_crossword_project_data({
            "product_type": "crossword",
            "title": "California Gold Rush Days",
            "is_book": True,
            "puzzle_count": 10,
            "fields": {
                "book_title": "California Gold Rush Days",
                "theme": "California Gold Rush Days",
                "output_format": "Full Book",
                "puzzles": "10",
                "creation_mode": "Topic (AI generates words)",
                "difficulty": "Easy",
                "include_answer_key": "Yes",
            },
            "cover_design": {
                "title": "California Gold Rush Days",
                "subtitle": "10 Crossword Puzzles - Easy Level",
            },
        })
        self.assertEqual(str(data["fields"]["puzzles"]), "12")
        self.assertEqual(data["puzzle_count"], 12)
        self.assertIn("12 Crossword Puzzles", data["cover_design"]["subtitle"])

    def test_twelve_puzzles_cover_keys_make_25_pages(self):
        puzzles, warnings, errors = build_crossword_puzzles(
            mode="topic",
            product_title="California Gold Rush Days",
            theme="California Gold Rush Days",
            difficulty="easy",
            grid_size=15,
            number_of_puzzles=12,
            words_per_puzzle=8,
            output_type="book",
            use_ai_words=False,
        )
        self.assertEqual(len(puzzles), 12, f"errors={errors}")
        pdf_bytes, layout = build_crossword_book_pdf_bytes(
            puzzles,
            product_title="California Gold Rush Days",
            subtitle="12 Crossword Puzzles - Easy Level",
            include_answer_key=True,
            cover_design={
                "title": "California Gold Rush Days",
                "subtitle": "12 Crossword Puzzles - Easy Level",
                "author": "",
            },
        )
        self.assertEqual(layout.page_count, 25)
        self.assertEqual(layout.cover_page_count, 1)
        self.assertEqual(layout.puzzle_page_count, 12)
        self.assertEqual(layout.answer_key_page_count, 12)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))


class TestBookContentQuality(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.puzzles, cls.warnings, cls.errors = build_crossword_puzzles(
            mode="topic",
            product_title="California Gold Rush Days",
            theme="California Gold Rush Days",
            difficulty="easy",
            grid_size=15,
            number_of_puzzles=12,
            words_per_puzzle=8,
            output_type="book",
            use_ai_words=False,
        )

    def test_every_puzzle_has_at_least_8_placed_answers(self):
        self.assertEqual(len(self.puzzles), 12)
        for idx, puzzle in enumerate(self.puzzles, 1):
            self.assertGreaterEqual(
                len(puzzle.placed_words), 8,
                f"Puzzle {idx} has {len(puzzle.placed_words)} placed answers",
            )

    def test_no_repeated_answers_across_book(self):
        seen: dict[str, int] = {}
        for idx, puzzle in enumerate(self.puzzles, 1):
            for word in puzzle.placed_words:
                key = word.upper()
                if key in seen:
                    self.fail(f"Duplicate answer {key} in puzzles {seen[key]} and {idx}")
                seen[key] = idx

    def test_no_repeated_clue_text_across_book(self):
        seen: dict[str, int] = {}
        for idx, puzzle in enumerate(self.puzzles, 1):
            for clue in puzzle.clues:
                key = clue.clue.strip().lower()
                if key in seen:
                    self.fail(f"Duplicate clue in puzzles {seen[key]} and {idx}: {key}")
                seen[key] = idx

    def test_no_unrelated_or_generic_fallback_vocabulary(self):
        all_answers = {w.upper() for p in self.puzzles for w in p.placed_words}
        forbidden = all_answers & _FORBIDDEN_ANSWERS
        self.assertFalse(forbidden, f"Forbidden answers present: {forbidden}")
        everyday_hits = all_answers & _EVERYDAY_SAMPLE
        # Everyday-life pack words must not appear for this Gold Rush theme.
        self.assertFalse(everyday_hits, f"Everyday Life words present: {everyday_hits}")
        for idx, puzzle in enumerate(self.puzzles, 1):
            for clue in puzzle.clues:
                low = clue.clue.lower()
                for snippet in _GENERIC_CLUE_SNIPPETS:
                    self.assertNotIn(
                        snippet, low,
                        f"Puzzle {idx} generic clue: {clue.clue}",
                    )


class TestExportPathAndCoverEntry(unittest.TestCase):
    def test_pdf_export_does_not_fall_through_to_ebook(self):
        from services.crossword.pdf_builder import CrosswordPdfRequest, build_crossword_pdf

        words, _warnings, _errors = suggest_crossword_words_from_topic(
            "California Gold Rush Days", max_words=120,
        )
        self.assertGreaterEqual(len(words), 96)
        req = CrosswordPdfRequest(
            product_title="California Gold Rush Days",
            theme="California Gold Rush Days",
            sub_topic="California Gold Rush Days",
            difficulty="easy",
            grid_size=15,
            number_of_puzzles=12,
            mode="topic",
            custom_words="\n".join(words),
            words_per_puzzle=8,
            include_answer_key=True,
            output_type="book",
            include_cover=True,
            cover_design={
                "title": "California Gold Rush Days",
                "subtitle": "12 Crossword Puzzles - Easy Level",
                "author": "",
                "use_ai_image": False,
            },
            use_ai_words=False,
            seed=42,
        )
        result = build_crossword_pdf(req)
        self.assertTrue(result.pdf_bytes.startswith(b"%PDF"), result.errors)
        self.assertEqual(result.render_engine, "crossword_direct")
        self.assertEqual(result.layout_info.get("page_count"), 25)
        self.assertNotIn("ebook", (result.render_engine or "").lower())

    def test_pdf_inside_zip_matches_direct_pdf(self):
        puzzles, warnings, errors = build_crossword_puzzles(
            mode="topic",
            product_title="California Gold Rush Days",
            theme="California Gold Rush Days",
            difficulty="easy",
            grid_size=15,
            number_of_puzzles=12,
            words_per_puzzle=8,
            output_type="book",
            use_ai_words=False,
            seed=7,
        )
        direct_pdf, layout = build_crossword_book_pdf_bytes(
            puzzles,
            product_title="California Gold Rush Days",
            subtitle="12 Crossword Puzzles - Easy Level",
            include_answer_key=True,
            cover_design={
                "title": "California Gold Rush Days",
                "subtitle": "12 Crossword Puzzles - Easy Level",
                "author": "",
            },
        )
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("california_gold_rush_days.pdf", direct_pdf)
        with zipfile.ZipFile(io.BytesIO(buf.getvalue()), "r") as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".pdf")]
            self.assertTrue(names)
            zipped_pdf = zf.read(names[0])
        self.assertEqual(
            hashlib.sha256(direct_pdf).hexdigest(),
            hashlib.sha256(zipped_pdf).hexdigest(),
        )
        self.assertEqual(layout.page_count, 25)

    def test_cover_editor_entry_visible_for_saved_crossword(self):
        app_js = os.path.join(
            os.path.dirname(__file__), "..", "static", "js", "app.js",
        )
        with open(app_js, encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn('coverBtn.textContent = "Edit Cover"', source)
        self.assertIn("openCoverEditor", source)
        self.assertIn("/cover-editor?project_id=", source)
        # After save, Edit Cover must be surfaced in the post-save path, not
        # only on the initial pre-save render when _project_id is still missing.
        self.assertIn("Edit Cover", source)
        post_save_idx = source.find("function renderPostSave")
        self.assertGreater(post_save_idx, 0)
        # Look in a window after renderPostSave for an Edit Cover injection.
        window = source[post_save_idx:post_save_idx + 8000]
        self.assertTrue(
            "Edit Cover" in window or "openCoverEditor" in window,
            "Edit Cover must be visible in the post-save Next Steps UI for saved crosswords",
        )
        # Submit path must force puzzles=12 even if the form field still says 10.
        collect_idx = source.find("function collectFactoryFields")
        self.assertGreater(collect_idx, 0)
        collect_window = source[collect_idx:collect_idx + 1200]
        self.assertIn('fields.puzzles = "12"', collect_window)

    def test_stale_ten_puzzle_saved_pdf_is_rebuilt_on_export(self):
        """Export must not re-serve a stored 21-page / 10-puzzle PDF."""
        import base64
        from pypdf import PdfReader, PdfWriter
        from reportlab.pdfgen import canvas
        from services.packaging import build_product_export
        from services.product import crossword_full_book_pdf_is_valid

        # Minimal invalid Full Book PDF: 21 blank pages, metadata says 10 puzzles.
        thin = io.BytesIO()
        c = canvas.Canvas(thin)
        for _ in range(21):
            c.drawString(72, 720, "stale thin crossword")
            c.showPage()
        c.save()
        writer = PdfWriter()
        writer.append(PdfReader(io.BytesIO(thin.getvalue())))
        writer.add_metadata({
            "/Title": "California Gold Rush Days",
            "/Subject": "10 Crossword Puzzles - Easy Level",
        })
        stale_buf = io.BytesIO()
        writer.write(stale_buf)
        stale_pdf = stale_buf.getvalue()
        self.assertFalse(crossword_full_book_pdf_is_valid(stale_pdf, expected_puzzles=12))

        project = {
            "id": None,
            "name": "California Gold Rush Days",
            "data": {
                "product_type": "crossword",
                "is_pdf": True,
                "is_book": True,
                "title": "California Gold Rush Days",
                "puzzle_count": 10,
                "pdf_bytes": base64.b64encode(stale_pdf).decode("ascii"),
                "filename": "california_gold_rush_days.pdf",
                "fields": {
                    "book_title": "California Gold Rush Days",
                    "theme": "California Gold Rush Days",
                    "output_format": "Full Book",
                    "puzzles": "10",
                    "creation_mode": "Topic (AI generates words)",
                    "difficulty": "Easy",
                    "include_answer_key": "Yes",
                    "include_cover": "Yes",
                },
                "cover_design": {
                    "title": "California Gold Rush Days",
                    "subtitle": "10 Crossword Puzzles - Easy Level",
                    "use_ai_image": False,
                },
            },
        }
        result = build_product_export(project)
        self.assertTrue(result.get("exports", {}).get("pdf_available"))
        files = result["exports"]["files"]
        pdf_url = files["pdf"]["url"]
        # Resolve package PDF from exports dir.
        from services.ebook_package import EXPORTS_DIR
        package_id = result["package_id"]
        pkg_dir = os.path.join(EXPORTS_DIR, package_id)
        pdf_path = None
        for name in os.listdir(pkg_dir):
            if name.lower().endswith(".pdf") and name != "ebook.pdf":
                pdf_path = os.path.join(pkg_dir, name)
                break
        self.assertIsNotNone(pdf_path, f"No product PDF in {os.listdir(pkg_dir)}")
        with open(pdf_path, "rb") as handle:
            exported = handle.read()
        self.assertTrue(crossword_full_book_pdf_is_valid(exported, expected_puzzles=12))
        reader = PdfReader(io.BytesIO(exported))
        self.assertEqual(len(reader.pages), 25)
        self.assertIn("12 Crossword Puzzles", str(reader.metadata.subject or ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
