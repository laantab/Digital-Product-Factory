"""Enforce medium quality, 24-call package budget, no retries, 300-DPI print prep."""
from __future__ import annotations

import base64
import io
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image


def _png_bytes(w: int = 64, h: int = 64, color=(0, 0, 0)) -> bytes:
    im = Image.new("RGB", (w, h), "white")
    px = im.load()
    for y in range(10, h - 10):
        for x in range(10, w - 10):
            px[x, y] = color
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


class TestPaidImageBudgetControls(unittest.TestCase):
    def tearDown(self):
        from services.ebook_package import reset_package_image_budgets

        reset_package_image_budgets()

    def test_budget_forces_quality_medium_never_auto_or_high(self):
        from services.ebook_package import (
            authorize_package_image_budget,
            authorize_paid_image_generation,
            generate_visual_image,
        )

        png = _png_bytes()
        mock_resp = MagicMock()
        mock_resp.data = [MagicMock(b64_json=base64.b64encode(png).decode("ascii"))]

        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "p01.png")
            client = MagicMock()
            client.images.generate.return_value = mock_resp
            client.images.edit = MagicMock(side_effect=AssertionError("edit disabled"))
            with patch("services.ebook_package.get_client", return_value=client):
                with authorize_paid_image_generation("test"):
                    with authorize_package_image_budget(
                        "tv_budget_q", max_attempts=24, quality="medium"
                    ):
                        ok = generate_visual_image(
                            "line art coloring page",
                            out,
                            size="1024x1536",
                            quality="medium",
                            package_id="tv_budget_q",
                            user_authorized=True,
                        )
                        self.assertTrue(ok)
                        kwargs = client.images.generate.call_args.kwargs
                        self.assertEqual(kwargs.get("quality"), "medium")
                        self.assertEqual(kwargs.get("size"), "1024x1536")
                        self.assertNotIn("auto", str(kwargs.get("quality")))
                        self.assertNotEqual(kwargs.get("quality"), "high")
                        client.images.edit.assert_not_called()

                with self.assertRaises(ValueError):
                    with authorize_package_image_budget(
                        "tv_budget_q", max_attempts=24, quality="high"
                    ):
                        pass
                with self.assertRaises(ValueError):
                    with authorize_package_image_budget(
                        "tv_budget_q", max_attempts=24, quality="auto"
                    ):
                        pass

    def test_hard_limit_24_counts_failed_attempts_and_stops(self):
        from services.ebook_package import (
            PaidImageBudgetExceeded,
            authorize_package_image_budget,
            authorize_paid_image_generation,
            generate_visual_image,
            get_package_image_budget,
        )

        client = MagicMock()
        client.images.generate.side_effect = RuntimeError("simulated API failure")

        with tempfile.TemporaryDirectory() as td:
            with patch("services.ebook_package.get_client", return_value=client):
                with authorize_paid_image_generation("test"):
                    with authorize_package_image_budget(
                        "tv_budget_24", max_attempts=24, quality="medium"
                    ):
                        for i in range(24):
                            out = os.path.join(td, f"p{i:02d}.png")
                            ok = generate_visual_image(
                                f"page {i}",
                                out,
                                size="1024x1536",
                                quality="medium",
                                package_id="tv_budget_24",
                                user_authorized=True,
                            )
                            self.assertFalse(ok)
                            self.assertFalse(os.path.isfile(out))

                        snap = get_package_image_budget("tv_budget_24")
                        self.assertEqual(snap["attempts"], 24)
                        self.assertEqual(snap["remaining"], 0)
                        self.assertEqual(client.images.generate.call_count, 24)

                        with self.assertRaises(PaidImageBudgetExceeded):
                            generate_visual_image(
                                "page overflow",
                                os.path.join(td, "overflow.png"),
                                size="1024x1536",
                                quality="medium",
                                package_id="tv_budget_24",
                                user_authorized=True,
                            )
                        # 25th network call must not happen.
                        self.assertEqual(client.images.generate.call_count, 24)

    def test_empty_response_counts_as_attempt_no_retry(self):
        from services.ebook_package import (
            authorize_package_image_budget,
            authorize_paid_image_generation,
            generate_visual_image,
            get_package_image_budget,
        )

        mock_resp = MagicMock()
        mock_resp.data = [MagicMock(b64_json=None)]
        client = MagicMock()
        client.images.generate.return_value = mock_resp

        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "empty.png")
            with patch("services.ebook_package.get_client", return_value=client):
                with authorize_paid_image_generation("test"):
                    with authorize_package_image_budget(
                        "tv_budget_empty", max_attempts=24, quality="medium"
                    ):
                        ok = generate_visual_image(
                            "empty payload",
                            out,
                            size="1024x1536",
                            quality="medium",
                            package_id="tv_budget_empty",
                            user_authorized=True,
                        )
                        self.assertFalse(ok)
                        self.assertEqual(client.images.generate.call_count, 1)
                        self.assertEqual(
                            get_package_image_budget("tv_budget_empty")["attempts"], 1
                        )
                        # No alternate-size second call.
                        sizes = [
                            c.kwargs.get("size")
                            for c in client.images.generate.call_args_list
                        ]
                        self.assertEqual(sizes, ["1024x1536"])

    def test_existing_file_reused_without_api_or_budget(self):
        from services.ebook_package import (
            authorize_package_image_budget,
            authorize_paid_image_generation,
            generate_visual_image,
            get_package_image_budget,
        )

        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "coloring_p10.png")
            open(out, "wb").write(_png_bytes())
            client = MagicMock()
            with patch("services.ebook_package.get_client", return_value=client):
                with authorize_paid_image_generation("test"):
                    with authorize_package_image_budget(
                        "tv_budget_reuse", max_attempts=24, quality="medium"
                    ):
                        ok = generate_visual_image(
                            "should not call",
                            out,
                            size="1024x1536",
                            quality="medium",
                            package_id="tv_budget_reuse",
                            user_authorized=True,
                        )
                        self.assertTrue(ok)
                        client.images.generate.assert_not_called()
                        self.assertEqual(
                            get_package_image_budget("tv_budget_reuse")["attempts"], 0
                        )

    def test_print_prep_300dpi_preserves_original(self):
        from services.coloring_book.line_art_layout import (
            PRINT_INTERIOR_SIZE,
            prepare_print_interior_300dpi,
        )

        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "coloring_p01.png")
            original = os.path.join(td, "originals", "coloring_p01_original.png")
            dst = os.path.join(td, "coloring_p01_print_300dpi.png")
            # Edge-pressed ink on API canvas.
            im = Image.new("RGB", (1024, 1536), "white")
            px = im.load()
            for y in range(0, 1500):
                for x in range(0, 1024):
                    if x < 4 or y < 4 or x > 1020:
                        px[x, y] = (0, 0, 0)
                    elif 200 < x < 800 and 200 < y < 1200:
                        px[x, y] = (0, 0, 0)
            im.save(src)

            metrics = prepare_print_interior_300dpi(
                src, dst, original_path=original
            )
            self.assertTrue(os.path.isfile(original))
            self.assertEqual(os.path.getsize(original), os.path.getsize(src))
            with Image.open(dst) as print_im:
                self.assertEqual(print_im.size, PRINT_INTERIOR_SIZE)
                self.assertEqual(print_im.size, (2250, 3000))
                dpi = print_im.info.get("dpi")
                self.assertIsNotNone(dpi)
                self.assertAlmostEqual(float(dpi[0]), 300.0, delta=1.0)
                self.assertAlmostEqual(float(dpi[1]), 300.0, delta=1.0)
            self.assertEqual(metrics["dpi"]["x"], 300)
            self.assertFalse(metrics["edge_contact"]["left"])
            self.assertFalse(metrics["edge_contact"]["right"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
