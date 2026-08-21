"""Paid image generation requires explicit user-approved generation actions."""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

THEME = (
    "Thunder Volt is a Black superhero. "
    "He is stopping two adult men from robbing a bank and getting away in New York City."
)


class TestPaidImageAuthorizationGuard(unittest.TestCase):
    def test_diagnostic_probe_cannot_call_image_api(self):
        from services.ebook_package import (
            PaidImageNotAuthorized,
            generate_visual_image,
            paid_image_generation_authorized,
        )

        self.assertFalse(paid_image_generation_authorized())
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "probe.png")
            with patch("services.ebook_package.get_client") as client:
                with self.assertRaises(PaidImageNotAuthorized):
                    generate_visual_image("diagnostic circle probe", out, size="1024x1536")
                client.assert_not_called()
            self.assertFalse(os.path.isfile(out))

    def test_qa_recheck_path_cannot_regenerate_via_api(self):
        from services.coloring_book.quality_agent import validate_coloring_book_pages
        from services.ebook_package import PaidImageNotAuthorized, generate_visual_image

        def bad_regen(prompt, path):
            return generate_visual_image(prompt, path, size="1024x1536")

        pages = [
            {
                "page_number": 10,
                "topic": "Thunder Volt Blocks the Getaway",
                "line_art_prompt": "x" * 40 + " line art coloring page featuring Thunder Volt",
                "image_path": os.path.join("nope", "missing.png"),
            }
        ]
        with patch("services.ebook_package.get_client") as client:
            # Missing image + regenerate callback must not reach the API.
            try:
                result = validate_coloring_book_pages(
                    pages,
                    main_character="Thunder Volt",
                    setting="New York City",
                    topic_field=THEME,
                    regenerate=True,
                    regenerate_fn=bad_regen,
                )
            except PaidImageNotAuthorized:
                client.assert_not_called()
                return
            client.assert_not_called()
            self.assertTrue(result.total_failed >= 1)

    def test_missing_file_reuse_does_not_auto_generate(self):
        from services.ebook_package import PaidImageNotAuthorized, generate_visual_image

        with tempfile.TemporaryDirectory() as td:
            missing = os.path.join(td, "coloring_p99.png")
            with patch("services.ebook_package.get_client") as client:
                with self.assertRaises(PaidImageNotAuthorized):
                    generate_visual_image("should not generate", missing, size="1024x1536")
                client.assert_not_called()

    def test_direct_client_images_generate_blocked_without_auth(self):
        """Ad-hoc diagnostic probes must not reach images.generate."""
        from services.ebook_package import (
            PaidImageNotAuthorized,
            generate_visual_image,
            paid_image_generation_authorized,
        )

        self.assertFalse(paid_image_generation_authorized())
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "diag_circle.png")
            with patch("services.ebook_package.get_client") as client:
                client.return_value.images.generate.side_effect = AssertionError(
                    "paid images.generate must not run"
                )
                with self.assertRaises(PaidImageNotAuthorized):
                    generate_visual_image(
                        "simple black and white line art circle on white background coloring page",
                        out,
                        size="1024x1536",
                    )
                client.assert_not_called()
            self.assertFalse(os.path.isfile(out))

    @patch("services.coloring_book.builder.generate_visual_image", side_effect=AssertionError("paid"))
    def test_save_export_basic_path_zero_paid(self, _img):
        from services.coloring_book.pdf_builder import ColoringBookPdfRequest, build_coloring_book_pdf
        from services.packaging import build_product_export
        import base64
        from reportlab.pdfgen import canvas
        import io

        result = build_coloring_book_pdf(
            ColoringBookPdfRequest(
                product_title="Thunder Volt",
                theme=THEME,
                page_count=2,
                include_cover=True,
                output_type="book",
                quality_mode="basic_test",
                package_id="tv_paid_guard_save",
                generation_stage="full",
            )
        )
        self.assertFalse(result.errors, result.errors)
        # Export must reuse bytes — never image API.
        with patch("services.ebook_package.generate_visual_image") as gen:
            from services.ebook_package import PaidImageNotAuthorized

            gen.side_effect = PaidImageNotAuthorized("blocked")
            buf = io.BytesIO()
            c = canvas.Canvas(buf)
            c.showPage()
            c.save()
            project = {
                "id": 910099,
                "name": "Thunder Volt",
                "data": {
                    "product_type": "coloring_book",
                    "is_pdf": True,
                    "is_book": True,
                    "title": "Thunder Volt",
                    "pdf_bytes": base64.b64encode(result.pdf_bytes or buf.getvalue()).decode("ascii"),
                    "package_id": "tv_paid_guard_save",
                    "filename": "thunder_volt.pdf",
                },
            }
            # If packaging somehow calls generate, this raises — export path must not.
            try:
                build_product_export(project)
            except PaidImageNotAuthorized:
                self.fail("Export path attempted paid image generation")
            gen.assert_not_called()

    def test_authorized_context_allows_call_path(self):
        from services.ebook_package import (
            authorize_paid_image_generation,
            generate_visual_image,
            paid_image_generation_authorized,
        )

        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "ok.png")
            # Existing file short-circuits without auth or client.
            open(out, "wb").write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
            self.assertTrue(generate_visual_image("noop", out))
            self.assertFalse(paid_image_generation_authorized())
            with authorize_paid_image_generation("test"):
                self.assertTrue(paid_image_generation_authorized())


class TestMarginFitLocal(unittest.TestCase):
    def test_fit_artwork_reduces_bbox_and_clears_edges(self):
        from PIL import Image, ImageDraw
        from services.coloring_book.line_art_layout import (
            fit_artwork_to_safe_margins,
            measure_line_art_layout,
        )

        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "src.png")
            dst = os.path.join(td, "dst.png")
            im = Image.new("RGB", (1024, 1536), "white")
            d = ImageDraw.Draw(im)
            # Ink pressed against three edges (fails margin gate).
            d.rectangle([0, 0, 1023, 1500], outline="black", width=6)
            d.ellipse([40, 40, 980, 1400], outline="black", width=4)
            im.save(src)
            before = measure_line_art_layout(src)
            self.assertGreater(before["bbox_coverage"], 0.92)
            metrics = fit_artwork_to_safe_margins(src, dst)
            self.assertTrue(os.path.isfile(dst))
            self.assertLessEqual(metrics["bbox_coverage"], 0.90)
            self.assertGreaterEqual(metrics["bbox_coverage"], 0.80)
            for side in ("left", "top", "right", "bottom"):
                self.assertFalse(metrics["edge_contact"][side], msg=side)
            self.assertEqual(metrics["width"], 1024)
            self.assertEqual(metrics["height"], 1536)


if __name__ == "__main__":
    unittest.main(verbosity=2)
