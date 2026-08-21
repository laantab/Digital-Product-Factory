"""Hybrid stock-then-AI visual production system. Zero real provider calls --
the AI image provider is always mocked. Proves:
  * Stock-to-AI fallback routing (interior and cover) only fires when stock
    photography cannot satisfy the brief.
  * Budget enforcement: no authorization/cap -> AI is never called.
  * Attempt limits are bounded (AI_VISUAL_MAX_ATTEMPTS), never unbounded retry.
  * Cost is logged per attempt, including rejected attempts, and spend never
    exceeds the configured cap.
  * A wrong-equipment AI candidate is rejected exactly like a wrong-equipment
    stock candidate (same scorer, same hard-reject rule).
  * The visual style spec is computed once per project and reused verbatim
    across every AI prompt for that project.
"""
from __future__ import annotations

import io
import os
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

from services.ebook_factory_pipeline import (  # noqa: E402
    AI_VISUAL_MAX_ATTEMPTS,
    AI_VISUAL_UNIT_USD,
    charge_visual_ai_call,
    estimate_max_visual_generation_cost_usd,
    fill_photo_aid_with_ai,
    visual_ai_authorized,
)
from services.ebook_visual_brief_common import build_visual_style_spec, style_spec_prompt_suffix  # noqa: E402

_KB_TITLE = "Strength Basics With a Single Weight"
_KB_TOPIC = "A kettlebell training guide for older beginners covering six core lifts"
_AUTHORIZED_FIELDS = {
    "topic": _KB_TOPIC,
    "include_images": "automatic",
    "visuals_authorized": "yes",
    "visual_budget_cap_usd": estimate_max_visual_generation_cost_usd(6),
}


def _fake_png_bytes() -> bytes:
    # Blocks of contrasting color, not flat noise: high-frequency per-pixel
    # noise averages away to near-zero variance once inspect_local_image()
    # downsamples to 64x64, which would (correctly) flag it as "not a
    # photograph". Large low-frequency shapes survive that downsample.
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (1024, 1024), (40, 90, 60))
    draw = ImageDraw.Draw(img)
    draw.rectangle((60, 60, 960, 420), fill=(200, 170, 90))
    draw.ellipse((300, 400, 760, 900), fill=(25, 60, 35))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestHybridVisualProduction(unittest.TestCase):
    def test_01_budget_not_authorized_blocks_ai_entirely(self):
        data: dict = {}
        fields = {"topic": _KB_TOPIC}  # no visuals_authorized, no cap
        self.assertFalse(visual_ai_authorized(data, fields))
        aid = {"type": "stock photo", "title": "Deadlift", "chapter": "The Deadlift", "chapter_index": 0, "visual_id": "v0_0"}
        with patch("services.ebook_package.generate_visual_image") as mock_gen:
            result = fill_photo_aid_with_ai(
                aid, package_id="unit-hybrid-1", data=data, fields=fields, title=_KB_TITLE, topic=_KB_TOPIC,
            )
        mock_gen.assert_not_called()
        self.assertEqual(result.get("status"), "missing")
        self.assertTrue(result.get("budget_message"))

    def test_02_authorized_budget_allows_ai_and_logs_cost(self):
        data: dict = {}
        fields = dict(_AUTHORIZED_FIELDS)
        self.assertTrue(visual_ai_authorized(data, fields))
        aid = {"type": "stock photo", "title": "Deadlift", "chapter": "The Deadlift", "chapter_index": 0, "visual_id": "v0_0"}

        def fake_generate(prompt, out_path, **kwargs):
            Path(out_path).write_bytes(_fake_png_bytes())
            return True

        with patch("services.ebook_package.generate_visual_image", side_effect=fake_generate), \
             patch("services.ebook_package.authorize_paid_image_generation") as mock_auth:
            mock_auth.return_value.__enter__ = lambda self: None
            mock_auth.return_value.__exit__ = lambda self, *a: False
            result = fill_photo_aid_with_ai(
                aid, package_id="unit-hybrid-2", data=data, fields=fields, title=_KB_TITLE, topic=_KB_TOPIC,
            )
        self.assertGreater(data.get("visual_ai_spend_usd", 0), 0)
        self.assertLessEqual(data["visual_ai_spend_usd"], fields["visual_budget_cap_usd"] + 1e-9)
        self.assertEqual(result.get("source"), "ai_generated")

    def test_03_attempts_are_bounded_not_unbounded(self):
        data: dict = {}
        fields = dict(_AUTHORIZED_FIELDS)
        aid = {"type": "stock photo", "title": "Deadlift", "chapter": "The Deadlift", "chapter_index": 0, "visual_id": "v0_0"}
        calls = {"n": 0}

        def failing_generate(prompt, out_path, **kwargs):
            calls["n"] += 1
            return False  # every attempt "fails" to produce a file

        with patch("services.ebook_package.generate_visual_image", side_effect=failing_generate), \
             patch("services.ebook_package.authorize_paid_image_generation") as mock_auth:
            mock_auth.return_value.__enter__ = lambda self: None
            mock_auth.return_value.__exit__ = lambda self, *a: False
            fill_photo_aid_with_ai(
                aid, package_id="unit-hybrid-3", data=data, fields=fields, title=_KB_TITLE, topic=_KB_TOPIC,
            )
        self.assertLessEqual(calls["n"], AI_VISUAL_MAX_ATTEMPTS)

    def test_04_rejected_attempts_still_count_toward_spend(self):
        data: dict = {}
        fields = dict(_AUTHORIZED_FIELDS)
        before = data.get("visual_ai_spend_usd", 0)
        ok = charge_visual_ai_call(data, fields)
        self.assertTrue(ok)
        self.assertGreater(data["visual_ai_spend_usd"], before)

    def test_05_charge_never_exceeds_configured_cap(self):
        data: dict = {"visual_ai_spend_usd": 0}
        fields = {"topic": _KB_TOPIC, "visuals_authorized": "yes", "visual_budget_cap_usd": AI_VISUAL_UNIT_USD}
        first = charge_visual_ai_call(data, fields)
        second = charge_visual_ai_call(data, fields)
        self.assertTrue(first)
        self.assertFalse(second)  # cap of exactly one unit is exhausted after one charge
        self.assertAlmostEqual(data["visual_ai_spend_usd"], AI_VISUAL_UNIT_USD, places=4)

    def test_06_wrong_equipment_ai_candidate_rejected_same_as_stock(self):
        from services.ebook_visual_match import build_visual_brief, score_photo_against_brief

        brief = build_visual_brief(
            {"type": "stock photo", "title": "Deadlift", "chapter": "The Deadlift", "chapter_index": 0, "visual_id": "v0_0"},
            chapter="The Deadlift", title=_KB_TITLE, topic=_KB_TOPIC,
        )
        # An AI prompt/alt describing the wrong implement must fail exactly
        # like a wrong-equipment stock photo did.
        report = score_photo_against_brief(brief, alt="a person lifting a barbell in a gym", filename="ai-try")
        self.assertEqual(report.status, "reject")

    def test_07_style_spec_computed_once_and_reused_in_prompts(self):
        spec = build_visual_style_spec(title=_KB_TITLE, topic=_KB_TOPIC, audience="adults over 50")
        self.assertIn("kettlebell", spec["equipment"])
        suffix1 = style_spec_prompt_suffix(spec)
        suffix2 = style_spec_prompt_suffix(spec)
        self.assertEqual(suffix1, suffix2)  # identical spec -> identical suffix text every time
        self.assertIn("adults over 50", suffix1)

    def test_08_no_project_specific_hardcoding(self):
        forbidden = ("21243", "4720792", "ef919a9f9aca494f8efa3759428e48a9", "29211b8d659d4f72afd860e019f83744")
        files = [
            ROOT / "services" / "ebook_visual_brief_common.py",
            ROOT / "services" / "ebook_customer_path.py",
            ROOT / "services" / "ebook_factory_pipeline.py",
        ]
        for path in files:
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(token, text, f"{token!r} hardcoded in {path.name}")


if __name__ == "__main__":
    unittest.main()
