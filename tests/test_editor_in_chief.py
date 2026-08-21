"""Editor-in-Chief release gate. Synthetic fixtures only; no external calls."""
from __future__ import annotations

import io
import os
import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ["FACTORY_TEST_MODE"] = "1"
os.environ["OPENAI_API_KEY"] = ""
os.environ["TAVILY_API_KEY"] = ""
os.environ["PEXELS_API_KEY"] = ""

from services.editor_in_chief import (  # noqa: E402
    CATEGORIES, MAX_CORRECTION_ROUNDS, VERDICT_BLOCKED, VERDICT_CORRECTION, VERDICT_PASS,
    CorrectionSession, Finding, ReviewReport, SelfApprovalError,
    KIND_JUDGMENT, KIND_OBJECTIVE, SEV_CRITICAL, SEV_MAJOR, SEV_MINOR,
    assert_independent_review, check_assets_present, check_chart_and_table_data,
    check_cross_project_duplication, check_customer_facing_leaks,
    check_identity_consistency, check_image_resolution, check_package_identity,
    check_page_count, check_page_quality, check_placeholder_and_leak, check_relevance,
    check_self_duplication, check_typography, check_visual_subject_verification,
    customer_ready, decide_verdict, defect_list, effective_dpi, inspect_image_file,
    is_safety_sensitive, score_categories,
)


def _png(path, size=(1200, 1200), pattern=True):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", size, (40, 90, 60))
    if pattern:
        d = ImageDraw.Draw(img)
        d.rectangle((size[0] // 12, size[1] // 12, size[0] * 5 // 6, size[1] // 3), fill=(210, 180, 90))
        d.ellipse((size[0] // 4, size[1] // 3, size[0] * 3 // 4, size[1] * 8 // 9), fill=(20, 60, 35))
    img.save(path)
    return str(path)


class TestIndependence(unittest.TestCase):
    def test_01_generator_cannot_approve_its_own_work(self):
        with self.assertRaises(SelfApprovalError):
            assert_independent_review(produced_by="ebook_production_agent",
                                      reviewed_by="ebook_production_agent")

    def test_02_independent_reviewer_is_accepted(self):
        assert_independent_review(produced_by="ebook_production_agent",
                                  reviewed_by="editor_in_chief")

    def test_03_missing_identity_is_refused(self):
        with self.assertRaises(SelfApprovalError):
            assert_independent_review(produced_by="x", reviewed_by="")

    def test_04_customer_ready_requires_pass(self):
        for v in (VERDICT_CORRECTION, VERDICT_BLOCKED):
            self.assertFalse(customer_ready(ReviewReport(verdict=v)))
        self.assertTrue(customer_ready(ReviewReport(verdict=VERDICT_PASS)))
        self.assertFalse(customer_ready(None))


class TestOriginality(unittest.TestCase):
    def test_05_detects_repeated_paragraph(self):
        para = "This paragraph is long enough to count as real duplicated body content here."
        f = check_self_duplication(f"# T\n\n{para}\n\nSomething else entirely.\n\n{para}\n")
        self.assertTrue(any(x.code == "ORIG_DUP_PARAGRAPH" for x in f))

    def test_06_ignores_short_repeats(self):
        self.assertEqual(check_self_duplication("Stop.\n\nGo on.\n\nStop.\n"), [])

    def test_07_detects_cross_project_copy(self):
        shared = ("A long shared passage that would clearly indicate one product was copied "
                  "wholesale from another product in the same library without any attribution "
                  "whatsoever, running well past the threshold that separates an incidental "
                  "phrase from genuine reuse of somebody else's written work.")
        f = check_cross_project_duplication(f"# A\n\n{shared}\n", {999: f"# B\n\n{shared}\n"})
        self.assertTrue(f and f[0].severity == SEV_CRITICAL)

    def test_07b_short_incidental_overlap_is_not_plagiarism(self):
        # A common phrase must never produce a plagiarism accusation.
        common = "Keep your back straight."
        self.assertEqual(
            check_cross_project_duplication(f"# A\n\n{common}\n", {999: f"# B\n\n{common}\n"}), [])

    def test_08_placeholder_and_prompt_leak_are_critical(self):
        for text in ("Chapter one. TODO finish this.", "As an AI language model, I cannot."):
            f = check_placeholder_and_leak(text)
            self.assertTrue(f, text)
            self.assertEqual(f[0].severity, SEV_CRITICAL)


class TestRelevance(unittest.TestCase):
    def test_09_flags_chapter_from_another_book(self):
        f = check_relevance("Sourdough Baking Basics",
                            [("Chapter 1", "Marine diesel engines require frequent impeller service.")])
        self.assertTrue(any(x.code == "REL_OFF_TOPIC" for x in f))

    def test_10_long_on_topic_chapter_is_not_flagged(self):
        # Guard against a length-sensitive relevance rule: a genuinely
        # on-topic chapter must not trip the check merely by being long.
        body = ("Sourdough starter needs regular feeding. " * 60) + \
               ("Baking a sourdough loaf rewards patience. " * 60)
        f = check_relevance("Sourdough Baking Basics", [("Feeding Your Starter", body)])
        self.assertEqual([x.code for x in f], [])

    def test_11_empty_chapter_is_critical(self):
        f = check_relevance("Any Title", [("Chapter 1", "   ")])
        self.assertTrue(f and f[0].severity == SEV_CRITICAL)


class TestConsistencyAndMetadata(unittest.TestCase):
    def test_12_blank_pdf_author_is_flagged(self):
        f = check_identity_consistency(title="T", author="Jane Doe", pdf_title="T", pdf_author="")
        self.assertTrue(any(x.code == "META_AUTHOR_MISSING" for x in f))

    def test_13_title_mismatch_is_flagged(self):
        f = check_identity_consistency(title="Real Title", author="A", pdf_title="Other", pdf_author="A")
        self.assertTrue(any(x.code == "META_TITLE_MISMATCH" for x in f))

    def test_14_page_count_disagreement_is_flagged(self):
        self.assertTrue(check_page_count(33, 34, 34))
        self.assertEqual(check_page_count(34, 34, 34), [])

    def test_15_toc_mismatch_is_flagged(self):
        f = check_identity_consistency(title="T", author="A", pdf_title="T", pdf_author="A",
                                       toc_titles=["One", "Two"], chapter_titles=["One", "Three"])
        self.assertTrue(any(x.code == "CONS_TOC_MISMATCH" for x in f))


class TestVisuals(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()

    def test_16_missing_asset_is_critical(self):
        f = check_assets_present([{"name": "gone.png", "path": os.path.join(self.tmp, "nope.png")}])
        self.assertTrue(f and f[0].code == "IMG_MISSING" and f[0].severity == SEV_CRITICAL)

    def test_17_flat_placeholder_image_is_critical(self):
        from PIL import Image
        p = os.path.join(self.tmp, "flat.png")
        Image.new("RGB", (900, 900), (128, 128, 128)).save(p)
        f = check_assets_present([{"name": "flat.png", "path": p}])
        self.assertTrue(any(x.code == "IMG_PLACEHOLDER" for x in f))

    def test_18_real_image_passes(self):
        p = _png(os.path.join(self.tmp, "ok.png"))
        self.assertEqual(check_assets_present([{"name": "ok.png", "path": p}]), [])

    def test_19_duplicate_image_reuse_is_flagged(self):
        p = _png(os.path.join(self.tmp, "a.png"))
        import shutil
        q = os.path.join(self.tmp, "b.png"); shutil.copyfile(p, q)
        f = check_assets_present([{"name": "a.png", "path": p}, {"name": "b.png", "path": q}])
        self.assertTrue(any(x.code == "IMG_DUPLICATE" for x in f))

    def test_20_low_resolution_blocks_print(self):
        self.assertEqual(effective_dpi(600, 6.0), 100)
        f = check_image_resolution([{"name": "low.png", "width": 600, "placed_inches": 6.0}])
        self.assertTrue(any(x.code == "IMG_DPI_BLOCK" and x.severity == SEV_CRITICAL for x in f))

    def test_21_review_and_target_bands(self):
        review = check_image_resolution([{"name": "m.png", "width": 1275, "placed_inches": 7.0}])
        self.assertTrue(any(x.code == "IMG_DPI_REVIEW" for x in review))
        sub = check_image_resolution([{"name": "s.png", "width": 1024, "placed_inches": 4.6}])
        self.assertTrue(any(x.code == "IMG_DPI_SUBTARGET" and x.severity == SEV_MINOR for x in sub))
        good = check_image_resolution([{"name": "g.png", "width": 2400, "placed_inches": 6.0}])
        self.assertEqual(good, [])

    def test_22_screen_only_skips_dpi_rules(self):
        f = check_image_resolution([{"name": "low.png", "width": 600, "placed_inches": 6.0}],
                                   print_product=False)
        self.assertEqual(f, [])


class TestSafetySensitive(unittest.TestCase):
    def test_23_detects_safety_sensitive_subjects(self):
        self.assertTrue(is_safety_sensitive("A strength training guide"))
        self.assertTrue(is_safety_sensitive("Using a power tool safely"))
        self.assertFalse(is_safety_sensitive("A memoir about coastal towns"))

    def test_24_unverified_safety_visual_blocks(self):
        f = check_visual_subject_verification(
            [{"name": "m.png", "kind": "photo", "location": "ch1"}],
            subject_text="kettlebell strength training for adults")
        self.assertTrue(f)
        self.assertEqual(f[0].kind, KIND_JUDGMENT)
        self.assertTrue(f[0].blocks(), "an unverified safety visual must block release")

    def test_25_human_verification_clears_it(self):
        f = check_visual_subject_verification(
            [{"name": "m.png", "kind": "photo", "subject_verified_by_human": True}],
            subject_text="strength training")
        self.assertEqual(f, [])

    def test_26_non_safety_subject_needs_no_verification(self):
        f = check_visual_subject_verification(
            [{"name": "m.png", "kind": "photo"}], subject_text="a memoir about coastal towns")
        self.assertEqual(f, [])


class TestChartsTablesPages(unittest.TestCase):
    def test_27_chart_without_data_is_critical(self):
        f = check_chart_and_table_data([{"type": "chart", "title": "c", "chart_data": {}}])
        self.assertTrue(any(x.code == "CHART_NO_DATA" for x in f))

    def test_28_chart_shape_mismatch_is_critical(self):
        f = check_chart_and_table_data([{"type": "chart", "title": "c",
                                         "chart_data": {"labels": ["a", "b"], "values": [1]}}])
        self.assertTrue(any(x.code == "CHART_SHAPE" for x in f))

    def test_29_unsourced_numeric_chart_needs_judgment(self):
        f = check_chart_and_table_data([{"type": "chart", "title": "c",
                                         "chart_data": {"labels": ["a"], "values": [1]}}])
        self.assertTrue(any(x.code == "CHART_NO_SOURCE" and x.kind == KIND_JUDGMENT for x in f))

    def test_30_em_dash_only_table_row_is_flagged(self):
        f = check_chart_and_table_data([{"type": "table", "title": "t",
                                         "table": {"headers": ["A", "B"], "rows": [["x", "—"]]}}])
        self.assertTrue(any(x.code == "TABLE_EMPTY_ROW" for x in f))

    def test_31_blank_rendered_page_is_critical(self):
        f = check_page_quality([{"page": 7, "ink_pct": 0.2, "midtone_pct": 0.1, "has_imagery": False}])
        self.assertTrue(f and f[0].code == "PAGE_BLANK" and f[0].severity == SEV_CRITICAL)


class TestTypographyAndLeaks(unittest.TestCase):
    def test_32_tiny_type_is_flagged(self):
        self.assertTrue(any(x.code == "A11Y_TEXT_TOO_SMALL"
                            for x in check_typography("p{font-size:6pt}")))
        self.assertEqual(check_typography("p{font-size:11pt}"), [])

    def test_33_broken_letter_spacing_is_flagged(self):
        self.assertTrue(any(x.code == "TYPO_LETTERSPACING"
                            for x in check_typography("h2{letter-spacing:0.9em}")))
        self.assertEqual(check_typography("h2{letter-spacing:0.02em}"), [])

    def test_34_localhost_and_local_paths_block(self):
        for doc in ("<a href='http://localhost:5000/x'>x</a>",
                    "<img src='file:///C:/tmp/a.png'>"):
            f = check_customer_facing_leaks(doc)
            self.assertTrue(f and f[0].severity == SEV_CRITICAL, doc)
        self.assertEqual(check_customer_facing_leaks("<p>clean</p>"), [])


class TestPackageIdentity(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.pdf = os.path.join(self.tmp, "ebook.pdf")
        open(self.pdf, "wb").write(b"%PDF-1.4\nbody\n%%EOF\n")
        import hashlib
        self.sha = hashlib.sha256(open(self.pdf, "rb").read()).hexdigest()
        self.zip = os.path.join(self.tmp, "package.zip")
        with zipfile.ZipFile(self.zip, "w") as z:
            z.write(self.pdf, "ebook.pdf")

    def test_35_matching_package_passes(self):
        self.assertEqual(check_package_identity(registered_pdf=self.pdf,
                                                served_pdf_sha=self.sha, zip_path=self.zip), [])

    def test_36_served_pdf_mismatch_is_critical(self):
        f = check_package_identity(registered_pdf=self.pdf, served_pdf_sha="deadbeef")
        self.assertTrue(any(x.code == "PKG_SERVED_MISMATCH" and x.severity == SEV_CRITICAL for x in f))

    def test_37_zip_pdf_mismatch_is_critical(self):
        bad = os.path.join(self.tmp, "bad.zip")
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("ebook.pdf", b"%PDF-1.4\ndifferent\n")
        f = check_package_identity(registered_pdf=self.pdf, zip_path=bad)
        self.assertTrue(any(x.code == "PKG_ZIP_PDF_MISMATCH" for x in f))

    def test_38_rollback_loss_is_critical(self):
        f = check_package_identity(registered_pdf=self.pdf, rollback_pdf=self.pdf,
                                   rollback_expected_sha="0" * 64)
        self.assertTrue(any(x.code == "PKG_ROLLBACK_LOST" and x.severity == SEV_CRITICAL for x in f))

    def test_39_rollback_intact_passes(self):
        f = check_package_identity(registered_pdf=self.pdf, rollback_pdf=self.pdf,
                                   rollback_expected_sha=self.sha)
        self.assertEqual(f, [])


class TestVerdictLogic(unittest.TestCase):
    def test_40_clean_candidate_passes(self):
        scores = score_categories([])
        v, overall = decide_verdict([], scores)
        self.assertEqual(v, VERDICT_PASS)
        self.assertEqual(overall, 10.0)

    def test_41_single_critical_defect_blocks_pass(self):
        f = [Finding(code="X", category="visual_quality", severity=SEV_CRITICAL,
                     kind=KIND_OBJECTIVE, summary="broken")]
        v, _ = decide_verdict(f, score_categories(f))
        self.assertEqual(v, VERDICT_CORRECTION)

    def test_42_unverifiable_judgment_yields_blocked_not_pass(self):
        f = [Finding(code="V", category="accuracy", severity=SEV_MAJOR,
                     kind=KIND_JUDGMENT, summary="needs a human")]
        v, _ = decide_verdict(f, score_categories(f))
        self.assertEqual(v, VERDICT_BLOCKED)

    def test_43_serious_defect_is_not_averaged_away(self):
        # Good grammar must not rescue a dangerous image.
        f = [Finding(code="D", category="accuracy", severity=SEV_CRITICAL,
                     kind=KIND_OBJECTIVE, summary="unsafe instructional image")]
        scores = score_categories(f)
        self.assertGreaterEqual(sum(scores.values()) / len(scores), 9.0)  # average still high
        v, _ = decide_verdict(f, scores)
        self.assertNotEqual(v, VERDICT_PASS)

    def test_44_package_integrity_must_be_perfect(self):
        f = [Finding(code="P", category="package_integrity", severity=SEV_MINOR,
                     kind=KIND_OBJECTIVE, summary="small packaging nit")]
        scores = score_categories(f)
        self.assertEqual(scores["package_integrity"], 9)
        v, _ = decide_verdict(f, scores)
        self.assertEqual(v, VERDICT_CORRECTION)

    def test_45_minor_defects_alone_can_still_pass(self):
        f = [Finding(code="M", category="interior_design", severity=SEV_MINOR,
                     kind=KIND_OBJECTIVE, summary="page a bit sparse")]
        v, _ = decide_verdict(f, score_categories(f))
        self.assertEqual(v, VERDICT_PASS)


class TestCorrectionLoop(unittest.TestCase):
    def test_46_correction_rounds_are_capped(self):
        s = CorrectionSession()
        for _ in range(MAX_CORRECTION_ROUNDS):
            self.assertTrue(s.may_correct())
            s.record(ReviewReport(verdict=VERDICT_CORRECTION))
        self.assertFalse(s.may_correct())
        self.assertIn("Stopping honestly", s.exhausted_message())

    def test_47_defect_list_is_numbered_and_assigned(self):
        rep = ReviewReport(findings=[
            Finding(code="A", category="package_integrity", severity=SEV_MINOR,
                    kind=KIND_OBJECTIVE, summary="minor"),
            Finding(code="B", category="visual_quality", severity=SEV_CRITICAL,
                    kind=KIND_OBJECTIVE, summary="critical"),
        ])
        d = defect_list(rep)
        self.assertEqual(d[0]["severity"], SEV_CRITICAL)   # critical ranks first
        self.assertEqual(d[0]["owner"], "visual_production")
        self.assertEqual([x["n"] for x in d], [1, 2])

    def test_48_customer_messages_never_leak_diagnostics(self):
        for v in (VERDICT_PASS, VERDICT_CORRECTION, VERDICT_BLOCKED):
            msg = ReviewReport(verdict=v).customer_message()
            for bad in ("sha", "digest", "/download/", "Traceback", ".png", "DPI"):
                self.assertNotIn(bad.lower(), msg.lower())


class TestExternalHonesty(unittest.TestCase):
    def test_49_external_plagiarism_is_never_assumed(self):
        rep = ReviewReport()
        self.assertFalse(rep.external_plagiarism_checked)

    def test_50_all_categories_are_scored(self):
        scores = score_categories([])
        self.assertEqual(set(scores), set(CATEGORIES))


if __name__ == "__main__":
    unittest.main()
