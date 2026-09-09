"""A book of identical text boxes is not an illustrated book.

WHAT SHIPPED
------------
A finished 44-page title passed every visual gate the Factory had and was not
sellable. Nine PNGs existed, one per chapter, each a valid file with a matching
hash and a caption — and eight were the same rounded box of text lines. No
photographs, no diagram, no chart.

Every existing check asked about one file at a time: does it exist, is it a
real PNG, does its hash match, is it captioned. None asked whether the book was
illustrated. "A PNG exists" had become the definition of "professional visual
approved".

These tests are written against the properties any illustrated non-fiction book
has, never against one book: variety of kind, some photographs where the
subject supports them, real data behind a chart, steps behind a diagram, no two
visuals sharing a design, and the visuals actually being inside the PDF rather
than beside it in the ZIP.

No external call is made by any test here.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("FACTORY_TEST_MODE", "1")

from services.ebook_visual_editorial import (  # noqa: E402
    ILLUSTRATIVE_TYPES,
    TEXT_BOX_TYPES,
    media_requirements,
    review_visual_set,
    verify_embedded_in_pdf,
)


def _aid(kind, vid, **over):
    aid = {
        "type": kind,
        "visual_id": vid,
        "required": True,
        "caption": f"Caption for {vid}.",
        "width": 1400,
        "height": 900,
        "source": "local",
    }
    if kind in {"photo", "stock photo"}:
        aid.update({
            "source": "pexels",
            "attribution": "Photograph by A. Person on Pexels",
            "width": 1920,
            "height": 1280,
            "detail_spread": 0.72,
        })
    if kind in {"checklist", "workflow", "timeline", "diagram"}:
        aid["items"] = [f"Step {i}" for i in range(1, 6)]
    if kind == "chart":
        aid["chart_data"] = {"labels": ["A", "B", "C"], "values": [1, 2, 3]}
    if kind in {"comparison", "comparison_table"}:
        aid["table"] = {"headers": ["A", "B"], "rows": [["1", "2"], ["3", "4"]]}
    aid.update(over)
    return aid


def _plan(*aids):
    return {
        "chapters": [
            {"chapter": f"Chapter {i}", "aids": [a]} for i, a in enumerate(aids, 1)
        ]
    }


def _review(*aids, **kw):
    kw.setdefault("photography_supported", True)
    kw.setdefault("chapter_count", len(aids))
    return review_visual_set(_plan(*aids), **kw)


def _text(findings):
    return " ".join(findings).lower()


# ------------------------------------------------ the set that shipped ---


class TheSetThatShippedTests(unittest.TestCase):
    def test_nine_text_boxes_are_rejected(self):
        """The exact shape of the defect: valid files, unusable book."""
        aids = [_aid("checklist", f"v_ch{i}", items=[f"Point {j}" for j in range(1, 7)])
                for i in range(1, 10)]
        report = _review(*aids)
        self.assertFalse(report.ok, "nine identical boxes were accepted as illustrations")
        self.assertIn("box of text lines", _text(report.findings))

    def test_the_rejection_survives_different_words_in_each_box(self):
        """Different text does not make it a different picture."""
        aids = [
            _aid("checklist", f"v_ch{i}", items=[f"Chapter {i} point {j}" for j in range(1, 7)])
            for i in range(1, 10)
        ]
        self.assertFalse(_review(*aids).ok)

    def test_alternating_two_box_types_is_still_not_illustrated(self):
        aids = [
            _aid("checklist" if i % 2 else "workflow", f"v_ch{i}")
            for i in range(1, 10)
        ]
        report = _review(*aids)
        self.assertFalse(report.ok)
        self.assertIn("box of text lines", _text(report.findings))


# -------------------------------------------------------- media variety ---


class MediaVarietyTests(unittest.TestCase):
    def test_a_varied_professional_set_passes(self):
        report = _review(
            _aid("photo", "v_ch1"),
            _aid("workflow", "v_ch2"),
            _aid("photo", "v_ch3"),
            _aid("timeline", "v_ch4", items=[f"Day {i}" for i in range(1, 8)]),
            _aid("photo", "v_ch5"),
            _aid("comparison", "v_ch6"),
            _aid("checklist", "v_ch7", items=["a", "b", "c", "d"]),
            _aid("photo", "v_ch8"),
            _aid("chart", "v_ch9"),
        )
        self.assertTrue(report.ok, f"a good set was rejected: {report.findings}")
        self.assertGreaterEqual(report.photograph_count, 3)

    def test_one_kind_may_not_dominate(self):
        aids = [_aid("comparison", f"v_ch{i}", table={
            "headers": ["A", "B"], "rows": [[str(i), "x"]] * (i + 1)})
            for i in range(1, 9)]
        aids.append(_aid("photo", "v_ch9"))
        report = _review(*aids)
        self.assertFalse(report.ok)
        self.assertIn("same kind", _text(report.findings))

    def test_photographs_are_required_when_the_subject_supports_them(self):
        report = _review(
            _aid("workflow", "v_ch1"),
            _aid("timeline", "v_ch2", items=["a", "b", "c"]),
            _aid("comparison", "v_ch3"),
            _aid("chart", "v_ch4"),
            photography_supported=True,
        )
        self.assertFalse(report.ok)
        self.assertIn("photograph", _text(report.findings))

    def test_a_book_whose_subject_admits_no_photography_is_not_punished(self):
        report = _review(
            _aid("comparison", "v_ch1"),
            _aid("chart", "v_ch2", chart_data={"labels": ["a", "b"], "values": [4, 9]}),
            _aid("timeline", "v_ch3", items=["a", "b", "c"]),
            _aid("workflow", "v_ch4", items=["p", "q", "r"]),
            photography_supported=False,
        )
        self.assertTrue(report.ok, report.findings)

    def test_the_requirement_scales_with_book_length(self):
        short = media_requirements(3, photography_supported=True)
        long = media_requirements(12, photography_supported=True)
        self.assertGreaterEqual(long["illustrative"], short["illustrative"])
        self.assertGreaterEqual(short["photographs"], 3)
        self.assertLessEqual(long["photographs"], 4)

    def test_the_two_type_families_do_not_overlap(self):
        self.assertFalse(TEXT_BOX_TYPES & ILLUSTRATIVE_TYPES)


# ------------------------------------------------------ honest content ---


class HonestContentTests(unittest.TestCase):
    def test_a_photograph_must_be_a_photograph(self):
        report = _review(
            _aid("photo", "v_ch1", source="local", attribution=""),
            _aid("photo", "v_ch2"),
            _aid("photo", "v_ch3"),
            _aid("workflow", "v_ch4"),
            _aid("comparison", "v_ch5"),
        )
        self.assertFalse(report.ok)
        self.assertIn("planned as a photograph", _text(report.findings))

    def test_a_flat_graphic_labelled_a_photograph_is_caught(self):
        report = _review(
            _aid("photo", "v_ch1", detail_spread=0.29),
            _aid("photo", "v_ch2"),
            _aid("photo", "v_ch3"),
            _aid("workflow", "v_ch4"),
            _aid("comparison", "v_ch5"),
        )
        self.assertFalse(report.ok)
        self.assertIn("flat graphic", _text(report.findings))

    def test_a_low_resolution_photograph_is_rejected(self):
        report = _review(
            _aid("photo", "v_ch1", width=640, height=420),
            _aid("photo", "v_ch2"),
            _aid("photo", "v_ch3"),
            _aid("workflow", "v_ch4"),
            _aid("comparison", "v_ch5"),
        )
        self.assertFalse(report.ok)
        self.assertIn("prints soft", _text(report.findings))

    def test_two_visuals_may_not_share_a_design(self):
        twin = dict(items=["a", "b", "c", "d", "e"])
        report = _review(
            _aid("checklist", "v_ch1", **twin),
            _aid("checklist", "v_ch2", **twin),
            _aid("photo", "v_ch3"),
            _aid("photo", "v_ch4"),
            _aid("photo", "v_ch5"),
            _aid("comparison", "v_ch6"),
        )
        self.assertFalse(report.ok)
        self.assertIn("repeats the design", _text(report.findings))

    def test_a_chart_needs_something_to_compare(self):
        report = _review(
            _aid("chart", "v_ch1", chart_data={"labels": ["only"], "values": [1]}),
            _aid("photo", "v_ch2"),
            _aid("photo", "v_ch3"),
            _aid("photo", "v_ch4"),
            _aid("comparison", "v_ch5"),
        )
        self.assertFalse(report.ok)
        self.assertIn("two data points", _text(report.findings))

    def test_research_sounding_figures_need_a_source(self):
        """No fabricated science, however plausible the label."""
        report = _review(
            _aid("chart", "v_ch1", title="Studies show a 47% improvement"),
            _aid("photo", "v_ch2"),
            _aid("photo", "v_ch3"),
            _aid("photo", "v_ch4"),
            _aid("comparison", "v_ch5"),
        )
        self.assertFalse(report.ok)
        self.assertIn("no source", _text(report.findings))

    def test_a_diagram_must_explain_a_sequence(self):
        report = _review(
            _aid("timeline", "v_ch1", items=["one step"]),
            _aid("photo", "v_ch2"),
            _aid("photo", "v_ch3"),
            _aid("photo", "v_ch4"),
            _aid("comparison", "v_ch5"),
        )
        self.assertFalse(report.ok)
        self.assertIn("does not explain a sequence", _text(report.findings))

    def test_captions_and_attribution_are_required(self):
        report = _review(
            _aid("photo", "v_ch1", caption=""),
            _aid("photo", "v_ch2", attribution=""),
            _aid("photo", "v_ch3"),
            _aid("workflow", "v_ch4"),
            _aid("comparison", "v_ch5"),
        )
        self.assertFalse(report.ok)
        text = _text(report.findings)
        self.assertIn("no caption", text)
        self.assertIn("no attribution", text)


# ------------------------------------------- inside the book, not beside ---


class EmbeddedInThePdfTests(unittest.TestCase):
    """A file in the exports folder is not a picture in the book."""

    def _pdf(self, tmp: Path, *, images: int) -> str:
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas
        from PIL import Image

        path = tmp / "book.pdf"
        c = canvas.Canvas(str(path))
        c.drawString(72, 720, "Cover")
        c.showPage()
        for i in range(images):
            swatch = Image.new("RGB", (240, 160), (30 + i * 10, 90, 120))
            c.drawImage(ImageReader(swatch), 72, 400, width=240, height=160)
            c.drawString(72, 320, f"Interior page {i + 1}")
            c.showPage()
        c.save()
        return str(path)

    def test_missing_images_are_reported(self):
        import tempfile

        tmp = Path(tempfile.mkdtemp(prefix="embed_"))
        pdf = self._pdf(tmp, images=1)
        plan = _plan(_aid("photo", "v_ch1"), _aid("photo", "v_ch2"), _aid("photo", "v_ch3"))
        report = verify_embedded_in_pdf(plan, pdf)
        self.assertFalse(report.ok)
        self.assertIn("not on a page", _text(report.findings))

    def test_present_images_pass(self):
        import tempfile

        tmp = Path(tempfile.mkdtemp(prefix="embed_ok_"))
        pdf = self._pdf(tmp, images=3)
        plan = _plan(_aid("photo", "v_ch1"), _aid("photo", "v_ch2"), _aid("photo", "v_ch3"))
        self.assertTrue(verify_embedded_in_pdf(plan, pdf).ok)

    def test_a_missing_pdf_is_a_finding_not_a_crash(self):
        report = verify_embedded_in_pdf(_plan(_aid("photo", "v_ch1")), "nowhere.pdf")
        self.assertFalse(report.ok)


# ------------------------------------------------- wired into approval ---


class PhotographyIsAllowedWhereItBelongsTests(unittest.TestCase):
    """"May this book have photographs?" is not "should it be mostly photographs?"

    Conflating the two is why a 44-page book about what people do with their
    attention shipped with nine text boxes and not one picture of a person.
    A mindfulness guide teaches a practice, so it is not photo-LED — and that
    strict answer was used as the gate on whether a photograph could appear at
    all.
    """

    def test_a_practice_book_may_have_photographs_without_being_photo_led(self):
        from services.ebook_visual_match import (
            is_photo_led_subject,
            photography_supported_subject,
        )

        title = "5-Minute Mindfulness for Busy Beginners"
        body = "Short daily practice for people at a desk. Sit, breathe, notice."
        self.assertFalse(is_photo_led_subject(title=title, content=body))
        self.assertTrue(
            photography_supported_subject(title=title, content=body),
            "a book about people practising cannot be illustrated",
        )

    def test_a_photo_led_subject_still_supports_photography(self):
        from services.ebook_visual_match import photography_supported_subject

        self.assertTrue(photography_supported_subject(
            title="Container Gardening on a Balcony", content="Pots, soil, plants."))

    def test_a_reference_work_is_not_forced_to_have_photographs(self):
        from services.ebook_visual_match import photography_supported_subject

        for title, body in (
            ("Federal Tax Table Reference", "A tax table reference and statute list."),
            ("API Reference Handbook", "api reference changelog glossary"),
        ):
            self.assertFalse(photography_supported_subject(title=title, content=body), title)


class APoorPlanIsNotReusedTests(unittest.TestCase):
    """"A plan exists" is not "the plan is any good".

    The pipeline reused any structurally valid plan forever, so a book whose
    plan was nine near-identical boxes could be rebuilt any number of times and
    would come back nine near-identical boxes. Nothing ever asked whether the
    plan was worth keeping — the same mistake as approving a visual because the
    PNG opens.
    """

    def _reuse_block(self):
        src = (ROOT / "services" / "ebook_visual_pipeline.py").read_text(encoding="utf-8")
        start = src.index("def prepare_visuals_for_review")
        return src[start:start + 4000]

    def test_reuse_is_conditional_on_the_editorial_verdict(self):
        body = self._reuse_block()
        self.assertIn("review_visual_set", body,
                      "a structurally valid plan is still reused unchecked")
        self.assertIn("reuse = False", body)

    def test_photographs_no_longer_depend_only_on_a_checkbox(self):
        body = self._reuse_block()
        self.assertIn("photography_supported_subject", body)
        self.assertIn("include_photographs=automatic or photographic", body)

    def test_replanning_keeps_photographs_already_found(self):
        """Replanning must not mean re-downloading."""
        import tempfile

        from services.ebook_visual_match import MATCH_PASS
        from services.ebook_visual_pipeline import _carry_over_resolved_photographs

        tmp = Path(tempfile.mkdtemp(prefix="carry_"))
        stored = tmp / "kept.png"
        stored.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)

        old = {"chapters": [{"chapter": "One", "aids": [{
            "type": "photo", "visual_id": "v_ch1", "chapter_index": 1,
            "match_status": MATCH_PASS, "asset_path": str(stored),
            "attribution": "Photographer on Pexels",
        }]}]}
        new = {"chapters": [{"chapter": "One", "aids": [{
            "type": "photo", "visual_id": "v_ch1", "chapter_index": 1,
            "status": "missing",
        }]}]}
        merged = _carry_over_resolved_photographs(old, new)
        kept = merged["chapters"][0]["aids"][0]
        self.assertEqual(kept["asset_path"], str(stored))
        self.assertEqual(kept["match_status"], MATCH_PASS)

    def test_an_unresolved_photograph_is_not_carried_over(self):
        from services.ebook_visual_pipeline import _carry_over_resolved_photographs

        old = {"chapters": [{"chapter": "One", "aids": [{
            "type": "photo", "visual_id": "v_ch1", "chapter_index": 1,
            "match_status": "REJECT", "asset_path": "gone.png"}]}]}
        new = {"chapters": [{"chapter": "One", "aids": [{
            "type": "photo", "visual_id": "v_ch1", "chapter_index": 1,
            "status": "missing"}]}]}
        merged = _carry_over_resolved_photographs(old, new)
        self.assertEqual(merged["chapters"][0]["aids"][0].get("status"), "missing")


class TheGateActuallyUsesThisTests(unittest.TestCase):
    def test_visual_readiness_consults_the_editorial_review(self):
        src = (ROOT / "services" / "ebook_visual_pipeline.py").read_text(encoding="utf-8")
        start = src.index("def validate_visual_readiness")
        body = src[start:src.index("\ndef ", start + 10)]
        self.assertIn("review_visual_set", body,
                      "the approval gate still judges files one at a time")

    def test_the_planner_commissions_a_mix_for_the_whole_book(self):
        src = (ROOT / "services" / "ebook_visual_pipeline.py").read_text(encoding="utf-8")
        start = src.index("def plan_content_aware_visuals")
        body = src[start:src.index("\ndef ", start + 10)]
        self.assertIn("_commission_media_mix", body)


if __name__ == "__main__":
    unittest.main()
