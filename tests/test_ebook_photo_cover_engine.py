"""Universal photo-cover typography engine. Zero paid/external calls.

Does not mutate live projects except read-only lock checks.
"""
from __future__ import annotations

import hashlib
import io
import os
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ["FACTORY_TEST_MODE"] = "1"
os.environ["PEXELS_API_KEY"] = ""

import database  # noqa: E402
from services.ebook_design_workspace import approve_visuals_local  # noqa: E402
from services.ebook_manuscript_engine import FROZEN_2472_SHA256  # noqa: E402
from services.ebook_manuscript_fixtures import build_event_photo_strong_manuscript  # noqa: E402
from services.ebook_photo_cover import (  # noqa: E402
    BLOCK_GAP,
    COVER_H,
    COVER_W,
    LAYOUT_IDS,
    MIN_AUTHOR_RENDER_PX,
    MIN_SUBTITLE_RENDER_PX,
    MIN_TITLE_RENDER_PX,
    PhotoCoverError,
    _cover_crop,
    _open_rgb_bytes,
    _prepare_photo,
    _thumb,
    attach_upload,
    default_editor,
    detect_subject_region,
    inspect_variant,
    plan_typography,
    render_layout,
    render_layout_with_qa,
    render_photo_variants,
    select_layout,
    assert_photo_cover_approvable,
    photo_cover_public_fields,
    _join_wrapped,
    NO_SAFE_COVER_MESSAGE,
    render_layout_with_recovery,
)
from services.ebook_project_workspace import (  # noqa: E402
    approve_stage,
    build_acceptance_project_data,
    manuscript_digest,
    set_stage_status,
)


def _solid(w=1600, h=2200, color=(30, 40, 55)) -> Image.Image:
    return Image.new("RGB", (w, h), color)


def _png(w=1600, h=2200, color=(30, 40, 55)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def _ident(**overrides) -> dict[str, str]:
    base = {
        "title": "Short Title",
        "subtitle": "A useful subtitle",
        "author": "Jane Author",
        "series": "",
    }
    base.update(overrides)
    return base


class UniversalPhotoCoverEngineTests(unittest.TestCase):
    def setUp(self):
        self._client_patch = patch("ai_client.get_client", side_effect=AssertionError("paid client"))
        self._chat_patch = patch("ai_client.chat", side_effect=AssertionError("paid chat"))
        self._json_patch = patch("ai_client.chat_json", side_effect=AssertionError("paid chat_json"))
        self._http = patch("services.ebook_pexels._http_get", side_effect=AssertionError("live http"))
        self._client_patch.start()
        self._chat_patch.start()
        self._json_patch.start()
        self._http.start()

    def tearDown(self):
        self._client_patch.stop()
        self._chat_patch.stop()
        self._json_patch.stop()
        self._http.stop()

    def _project(self, **identity) -> tuple[int, dict]:
        data = build_acceptance_project_data()
        data["acceptance_marker"] = None
        pkg = f"ebook-engine-{uuid.uuid4().hex[:16]}"
        data["artifact_id"] = pkg
        data["package_id"] = pkg
        md = build_event_photo_strong_manuscript()
        data["content"] = md
        data["ebook"] = md
        data["ebook_workspace"]["marker"] = None
        if identity:
            data.update(identity)
        set_stage_status(data["ebook_workspace"], "manuscript", "awaiting_approval")
        data = approve_stage(data, "manuscript")
        data = approve_visuals_local(data)
        project = database.create_project(
            "Photo Cover Engine Isolated",
            "ebook",
            data,
            user_saved=False,
            system_test=True,
            temporary=True,
        )
        pid = project["id"]
        data["_project_id"] = pid
        database.update_project(pid, None, data)
        return pid, dict(database.get_project(pid)["data"])

    def test_01_engine_has_no_hardcoded_project_or_topic_copy(self):
        src = (ROOT / "services" / "ebook_photo_cover.py").read_text(encoding="utf-8")
        self.assertNotIn("4249", src)
        self.assertNotIn("Lonnie Brown", src)
        self.assertNotIn("Dye-Sublimation", src)
        self.assertNotIn("event_photography", src)
        self.assertIn("plan_typography", src)

    def test_02_short_and_long_titles_wrap_without_splitting_words(self):
        editor = default_editor()
        photo = _solid()
        short = _ident(title="Go")
        long = _ident(title="Practical Field Methods For On Site Event Photography Teams")
        for ident in (short, long):
            for lid in LAYOUT_IDS:
                img, qa = render_layout_with_qa(photo, lid, ident, editor)
                self.assertTrue(qa["pass"], (lid, ident["title"], qa.get("findings")))
                self.assertEqual(img.size, (COVER_W, COVER_H))
                cropped = _cover_crop(_prepare_photo(photo), editor)
                plan = plan_typography(ident, editor, lid, cropped)
                title_block = next(b for b in plan["blocks"] if b["role"] == "title")
                joined = _join_wrapped(title_block["lines"])
                self.assertEqual(joined, ident["title"])
                for line in title_block["lines"]:
                    self.assertTrue(all(word in ident["title"] for word in line.split()))

    def test_03_missing_and_long_subtitles(self):
        editor = default_editor()
        photo = _solid()
        missing = _ident(subtitle="")
        long = _ident(
            subtitle=(
                "A Practical Guide to Equipment, Pricing, Client Workflow, "
                "Event-Day Operations, and Dye-Sublimation Printing"
            )
        )
        for ident in (missing, long):
            for lid in LAYOUT_IDS:
                _img, qa = render_layout_with_qa(photo, lid, ident, editor)
                self.assertTrue(qa["pass"], (lid, ident["subtitle"][:20], qa.get("findings")))
        plan = plan_typography(missing, editor, "full_bleed_editorial", photo)
        self.assertFalse(any(b["role"] == "subtitle" for b in plan["blocks"]))

    def test_04_short_and_long_authors_and_optional_series(self):
        editor = default_editor()
        photo = _solid()
        cases = (
            _ident(author="Li"),
            _ident(author="Jane Elizabeth Harrington-Cole"),
            _ident(series="Field Notes Volume Two"),
        )
        for ident in cases:
            for lid in LAYOUT_IDS:
                _img, qa = render_layout_with_qa(photo, lid, ident, editor)
                self.assertTrue(qa["pass"], (lid, ident, qa.get("findings")))
        plan = plan_typography(cases[2], editor, "full_bleed_editorial", photo)
        series = next(b for b in plan["blocks"] if b["role"] == "series")
        self.assertEqual(_join_wrapped(series["lines"]), "Field Notes Volume Two")

    def test_05_landscape_portrait_square_and_exif_crop_full_bleed(self):
        editor = {**default_editor(), "zoom": 1.0, "focal_x": 0.5, "focal_y": 0.5}
        shots = {
            "landscape": Image.new("RGB", (2400, 1400), (40, 80, 40)),
            "portrait": Image.new("RGB", (1400, 2400), (40, 40, 80)),
            "square": Image.new("RGB", (1800, 1800), (80, 40, 40)),
        }
        for name, im in shots.items():
            cropped = _cover_crop(_prepare_photo(im), editor)
            self.assertEqual(cropped.size, (COVER_W, COVER_H), name)
            for xy in ((1, 1), (COVER_W - 2, 1), (1, COVER_H - 2), (COVER_W - 2, COVER_H - 2)):
                px = cropped.getpixel(xy)
                self.assertFalse(all(c > 240 for c in px[:3]), (name, xy, px))
        stored = Image.new("RGB", (1800, 1000), (18, 48, 88))
        ImageDraw.Draw(stored).rectangle((0, 0, 1800, 70), fill=(230, 24, 24))
        buf = io.BytesIO()
        exif = Image.Exif()
        exif[0x0112] = 6
        stored.save(buf, format="JPEG", quality=95, exif=exif)
        opened = _open_rgb_bytes(buf.getvalue())
        self.assertEqual(opened.size, (1000, 1800))
        cropped = _cover_crop(_prepare_photo(opened), editor)
        self.assertEqual(cropped.size, (COVER_W, COVER_H))

    def test_06_bright_dark_mixed_contrast_and_no_distortion(self):
        editor = default_editor()
        ident = _ident()
        photos = {
            "dark": _solid(color=(12, 16, 22)),
            "bright": _solid(color=(230, 228, 220)),
            "mixed": Image.new("RGB", (1600, 2200), (230, 228, 220)),
        }
        ImageDraw.Draw(photos["mixed"]).rectangle((0, 1100, 1600, 2200), fill=(16, 18, 24))
        for name, photo in photos.items():
            for lid in LAYOUT_IDS:
                img, qa = render_layout_with_qa(photo, lid, ident, editor)
                self.assertTrue(qa["pass"], (name, lid, qa.get("findings")))
                self.assertEqual(img.size, (COVER_W, COVER_H))
        circle = Image.new("RGB", (2000, 1200), (22, 28, 36))
        ImageDraw.Draw(circle).ellipse((700, 300, 1300, 900), fill=(210, 32, 32))
        cropped = _cover_crop(circle, {**editor, "zoom": 1.0, "focal_x": 0.5, "focal_y": 0.5})
        pix = cropped.load()
        xs, ys = [], []
        for y in range(0, COVER_H, 2):
            for x in range(0, COVER_W, 2):
                r, g, b = pix[x, y]
                if r > 150 and r > g + 60 and r > b + 60:
                    xs.append(x)
                    ys.append(y)
        ratio = (max(xs) - min(xs)) / max(max(ys) - min(ys), 1)
        self.assertGreater(ratio, 0.88)
        self.assertLess(ratio, 1.12)

    def test_07_extreme_focal_zoom_never_exposes_blank(self):
        photo = _solid(color=(28, 66, 48))
        editor = {**default_editor(), "zoom": 2.4, "focal_x": 0.08, "focal_y": 0.92}
        cropped = _cover_crop(_prepare_photo(photo), editor)
        self.assertEqual(cropped.size, (COVER_W, COVER_H))
        for xy in ((2, 2), (COVER_W - 3, 2), (2, COVER_H - 3), (COVER_W - 3, COVER_H - 3)):
            px = cropped.getpixel(xy)
            self.assertFalse(all(c > 240 for c in px[:3]), xy)

    def test_08_unbreakable_word_fails_instead_of_clipping(self):
        ident = _ident(title="Supercalifragilisticexpialidociousantidisestablishmentarianism")
        plan = plan_typography(ident, default_editor(), "full_bleed_editorial")
        self.assertFalse(plan["pass"])
        self.assertTrue(set(plan["findings"]) & {"word_too_wide", "text_does_not_fit"})

    def test_09_failed_variants_hidden_and_approval_blocked(self):
        pid, data = self._project(
            title="Supercalifragilisticexpialidociousantidisestablishmentarianism",
            subtitle="Ok",
            author="A",
        )
        data = attach_upload(data, _png(), filename="ok.png", license_note="Owned.", project_id=pid, owned=True)
        public = photo_cover_public_fields(data, project_id=pid)
        self.assertEqual(public["passing_count"], 0)
        self.assertTrue(public["failed_variants"])
        self.assertTrue(all(not row["quality_pass"] for row in public["variants"]))
        self.assertTrue(all(not row["full_url"] for row in public["variants"]))
        self.assertEqual(public["workflow_step"], "choose_another_photo")
        self.assertEqual(public["user_status"], NO_SAFE_COVER_MESSAGE)
        self.assertTrue(public["no_safe_cover"])
        self.assertFalse(public["approvable"])
        with self.assertRaises(PhotoCoverError):
            select_layout(data, "full_bleed_editorial", project_id=pid)
        with self.assertRaises(PhotoCoverError):
            assert_photo_cover_approvable(data, project_id=pid)
        self.assertFalse(public["approvable"])

    def test_10_three_passing_variants_when_text_fits(self):
        pid, data = self._project(title="Field Guide", subtitle="Practical methods", author="Ada West")
        data = attach_upload(data, _png(), filename="ok.png", license_note="Owned.", project_id=pid, owned=True)
        cover = data["cover_design"]
        self.assertEqual(set(cover["variants"]), set(LAYOUT_IDS))
        for lid, row in cover["variants"].items():
            self.assertTrue(row["quality"]["pass"], (lid, row["quality"].get("findings")))
            self.assertTrue(os.path.isfile(row["png_path"]))
            self.assertTrue(os.path.isfile(row["thumb_path"]))
            self.assertTrue(os.path.isfile(row["pdf_path"]))
            thumb = Image.open(row["thumb_path"])
            full = Image.open(row["png_path"])
            self.assertEqual(full.size, (COVER_W, COVER_H))
            self.assertEqual(thumb.size, _thumb(full).size)
            self.assertEqual(row["png_digest"], hashlib.sha256(open(row["png_path"], "rb").read()).hexdigest())
            self.assertEqual(row["digest"], hashlib.sha256(open(row["pdf_path"], "rb").read()).hexdigest())

    def test_11_preview_pdf_bytes_are_the_selected_variant(self):
        pid, data = self._project(title="Field Guide", subtitle="Practical methods", author="Ada West")
        data = attach_upload(data, _png(), filename="ok.png", license_note="Owned.", project_id=pid, owned=True)
        data = select_layout(data, "full_bleed_editorial", project_id=pid)
        chosen = data["cover_design"]["variants"]["full_bleed_editorial"]
        pdf = open(chosen["pdf_path"], "rb").read()
        self.assertEqual(hashlib.sha256(pdf).hexdigest(), data["cover_design"]["cover_digest"])
        self.assertEqual(chosen["pdf_path"], data["cover_design"]["local_cover_pdf"])
        self.assertEqual(open(data["cover_design"]["local_cover_pdf"], "rb").read(), pdf)

    def test_12_locked_live_projects_immutable_during_isolated_render(self):
        live = database.get_project(2472)
        before_2472 = hashlib.sha256(str(live["data"].get("content") or "").encode("utf-8")).hexdigest()
        before_4249 = None
        row = database.get_project(4249)
        if row:
            before_4249 = manuscript_digest(row["data"])
        pid, data = self._project(title="Isolated", subtitle="Only this project", author="Pat")
        attach_upload(data, _png(), filename="ok.png", license_note="Owned.", project_id=pid, owned=True)
        after_2472 = hashlib.sha256(
            str(database.get_project(2472)["data"].get("content") or "").encode("utf-8")
        ).hexdigest()
        self.assertEqual(after_2472, before_2472)
        self.assertEqual(after_2472, FROZEN_2472_SHA256)
        if before_4249 is not None:
            self.assertEqual(manuscript_digest(database.get_project(4249)["data"]), before_4249)

    def test_13_never_rewrites_approved_text(self):
        ident = _ident(
            title="From First Booking to On-Site Prints",
            subtitle="Keep every approved word exactly",
            author="Ada West",
        )
        plan = plan_typography(ident, default_editor(), "split_studio")
        self.assertTrue(plan["pass"], plan.get("findings"))
        by_role = {b["role"]: _join_wrapped(b["lines"]) for b in plan["blocks"]}
        self.assertEqual(by_role["title"], ident["title"])
        self.assertEqual(by_role["subtitle"], ident["subtitle"])
        self.assertEqual(by_role["author"], ident["author"])

    def test_14_long_title_and_long_subtitle_wrap_at_readable_size(self):
        ident = _ident(
            title="Practical Field Methods For On Site Event Photography Teams",
            subtitle=(
                "A Practical Guide to Equipment, Pricing, Client Workflow, "
                "Event-Day Operations, and Dye-Sublimation Printing"
            ),
        )
        plan = plan_typography(ident, default_editor(), "full_bleed_editorial", _solid())
        self.assertTrue(plan["pass"], plan.get("findings"))
        sub = next(b for b in plan["blocks"] if b["role"] == "subtitle")
        title = next(b for b in plan["blocks"] if b["role"] == "title")
        self.assertGreaterEqual(len(sub["lines"]), 3)
        self.assertGreaterEqual(sub["size"], MIN_SUBTITLE_RENDER_PX)
        self.assertGreaterEqual(title["size"], MIN_TITLE_RENDER_PX)
        self.assertEqual(_join_wrapped(sub["lines"]), ident["subtitle"])
        self.assertEqual(_join_wrapped(title["lines"]), ident["title"])
        gap = sub["y"] - (title["y"] + title["h"])
        self.assertGreaterEqual(gap, BLOCK_GAP - 2)

    def test_15_multiline_subtitle_is_preferred_over_shrinking(self):
        ident = _ident(
            subtitle=(
                "A Practical Guide to Equipment, Pricing, Client Workflow, "
                "Event-Day Operations, and Dye-Sublimation Printing"
            )
        )
        plan = plan_typography(ident, default_editor(), "full_bleed_editorial")
        sub = next(b for b in plan["blocks"] if b["role"] == "subtitle")
        self.assertGreaterEqual(len(sub["lines"]), 3)
        self.assertLessEqual(len(sub["lines"]), 6)
        self.assertGreaterEqual(sub["size"], MIN_SUBTITLE_RENDER_PX)
        longest = max(len(line) for line in sub["lines"])
        shortest = min(len(line) for line in sub["lines"])
        self.assertLess(longest - shortest, 40)

    def test_16_minimum_readable_font_sizes_are_enforced_after_shrink(self):
        self.assertGreaterEqual(MIN_TITLE_RENDER_PX, 48)
        self.assertGreaterEqual(MIN_SUBTITLE_RENDER_PX, 44)
        self.assertGreaterEqual(MIN_AUTHOR_RENDER_PX, 26)
        ident = _ident(
            title="From First Booking to On-Site Prints",
            subtitle=(
                "A Practical Guide to Equipment, Pricing, Client Workflow, "
                "Event-Day Operations, and Dye-Sublimation Printing"
            ),
            author="Ada West",
        )
        for lid in LAYOUT_IDS:
            img, qa = render_layout_with_qa(_solid(), lid, ident, default_editor())
            if not qa["pass"]:
                self.assertTrue(qa["findings"])
                continue
            sizes = qa["plan_sizes"]
            self.assertGreaterEqual(sizes["title"], MIN_TITLE_RENDER_PX, (lid, sizes))
            self.assertGreaterEqual(sizes["subtitle"], MIN_SUBTITLE_RENDER_PX, (lid, sizes))
            self.assertGreaterEqual(sizes["author"], MIN_AUTHOR_RENDER_PX, (lid, sizes))
            self.assertEqual(img.size, (COVER_W, COVER_H))

    def test_17_tiny_unclipped_text_is_rejected(self):
        ident = _ident(subtitle="Tiny but fully inside the canvas")
        plan = plan_typography(ident, default_editor(), "full_bleed_editorial", _solid())
        fake = dict(plan)
        fake["pass"] = True
        fake["findings"] = []
        blocks = []
        for block in plan["blocks"]:
            row = dict(block)
            if row["role"] == "subtitle":
                row["size"] = 18
            blocks.append(row)
        fake["blocks"] = blocks
        fake["sizes"] = {**(plan.get("sizes") or {}), "subtitle": 18}
        qa = inspect_variant(_solid(COVER_W, COVER_H), "full_bleed_editorial", ident, plan=fake)
        self.assertFalse(qa["pass"])
        self.assertTrue(set(qa["findings"]) & {"subtitle_unreadable", "subtitle_unreadable_at_thumbnail"})

    def test_18_subject_safe_placement_hides_overlap_layouts(self):
        photo = Image.new("RGB", (1600, 2200), (16, 18, 28))
        draw = ImageDraw.Draw(photo)
        draw.ellipse((700, 350, 1100, 900), fill=(198, 148, 118))
        draw.rectangle((780, 900, 1020, 1800), fill=(70, 92, 78))
        ident = _ident(
            title="From First Booking to On-Site Prints",
            subtitle=(
                "A Practical Guide to Equipment, Pricing, Client Workflow, "
                "Event-Day Operations, and Dye-Sublimation Printing"
            ),
        )
        cropped = _cover_crop(photo, default_editor())
        subject = detect_subject_region(cropped, default_editor())
        self.assertIsNotNone(subject)
        results = {}
        for lid in LAYOUT_IDS:
            img, qa = render_layout_with_qa(photo, lid, ident, default_editor())
            results[lid] = qa
            self.assertEqual(img.size, (COVER_W, COVER_H))
        self.assertTrue(
            results["full_bleed_editorial"]["pass"], results["full_bleed_editorial"].get("findings")
        )
        top = plan_typography(ident, default_editor(), "full_bleed_editorial", cropped, subject=subject)
        face = subject["face_box"]
        sub = next(b for b in top["blocks"] if b["role"] == "subtitle")
        self.assertLessEqual(len(sub["lines"]), 6)
        self.assertGreaterEqual(max(len(line) for line in sub["lines"]), 28)
        for block in top["blocks"]:
            if block["role"] == "author":
                continue
            hits = block.get("line_boxes") or [block["box"]]
            for hit in hits:
                self.assertFalse(_boxes_overlap_local(hit, face), (block["role"], hit, face))
        passing = [lid for lid, qa in results.items() if qa.get("pass")]
        self.assertIn("full_bleed_editorial", passing)
        for lid in passing:
            self.assertNotIn("subject_overlap", results[lid].get("findings") or [], lid)
        forced = dict(top)
        forced["pass"] = True
        forced["findings"] = []
        overlap_block = dict(top["blocks"][0])
        overlap_block["box"] = face
        overlap_block["line_boxes"] = [face]
        forced["blocks"] = [overlap_block]
        qa_overlap = inspect_variant(cropped, "split_studio", ident, plan=forced, subject=subject)
        self.assertIn("subject_overlap", qa_overlap["findings"])

    def test_19_safe_margins_and_text_block_spacing(self):
        ident = _ident(
            title="From First Booking to On-Site Prints",
            subtitle=(
                "A Practical Guide to Equipment, Pricing, Client Workflow, "
                "Event-Day Operations, and Dye-Sublimation Printing"
            ),
        )
        plan = plan_typography(ident, default_editor(), "full_bleed_editorial", _solid())
        self.assertTrue(plan["pass"], plan.get("findings"))
        margin_x = int(COVER_W * 0.07)
        margin_y = int(COVER_H * 0.05)
        by_role = {b["role"]: b for b in plan["blocks"]}
        for block in plan["blocks"]:
            x0, y0, x1, y1 = block["box"]
            self.assertGreaterEqual(x0, margin_x - 1)
            self.assertGreaterEqual(y0, margin_y - 1)
            self.assertLessEqual(x1, COVER_W - margin_x + 1)
            self.assertLessEqual(y1, COVER_H - margin_y + 1)
        gap = by_role["subtitle"]["y"] - (by_role["title"]["y"] + by_role["title"]["h"])
        self.assertGreaterEqual(gap, BLOCK_GAP - 2)
        author = by_role["author"]
        self.assertLess(author["x"], COVER_W * 0.20)
        self.assertGreater(author["y"], COVER_H * 0.80)

    def test_20_thumbnail_is_generated_from_full_size_cover(self):
        pid, data = self._project(
            title="Field Guide", subtitle="Practical methods for field teams", author="Ada West"
        )
        data = attach_upload(data, _png(), filename="ok.png", license_note="Owned.", project_id=pid, owned=True)
        for lid, row in data["cover_design"]["variants"].items():
            if not (row.get("quality") or {}).get("pass"):
                continue
            full = Image.open(row["png_path"]).convert("RGB")
            thumb = Image.open(row["thumb_path"]).convert("RGB")
            self.assertEqual(full.size, (COVER_W, COVER_H), lid)
            expected = _thumb(full)
            self.assertEqual(thumb.size, expected.size, lid)
            self.assertEqual(thumb.tobytes(), expected.tobytes(), lid)

    def test_21_approval_blocked_for_failed_variants(self):
        ident = _ident(title="Supercalifragilisticexpialidociousantidisestablishmentarianism")
        plan = plan_typography(ident, default_editor(), "full_bleed_editorial")
        self.assertFalse(plan["pass"])
        pid, data = self._project(
            title="Supercalifragilisticexpialidociousantidisestablishmentarianism",
            subtitle="Ok",
            author="A",
        )
        data = attach_upload(data, _png(), filename="ok.png", license_note="Owned.", project_id=pid, owned=True)
        public = photo_cover_public_fields(data, project_id=pid)
        self.assertEqual(public["passing_count"], 0)
        self.assertTrue(all(not row["full_url"] for row in public["variants"]))
        self.assertFalse(public["approvable"])
        with self.assertRaises(PhotoCoverError):
            assert_photo_cover_approvable(data, project_id=pid)

    def test_22_no_distortion_or_blank_space_after_readable_type(self):
        ident = _ident(
            title="From First Booking to On-Site Prints",
            subtitle=(
                "A Practical Guide to Equipment, Pricing, Client Workflow, "
                "Event-Day Operations, and Dye-Sublimation Printing"
            ),
        )
        img, qa = render_layout_with_qa(
            _solid(color=(28, 66, 48)), "full_bleed_editorial", ident, default_editor()
        )
        self.assertTrue(qa["pass"], qa.get("findings"))
        self.assertEqual(img.size, (COVER_W, COVER_H))
        for xy in ((2, 2), (COVER_W - 3, 2), (2, COVER_H - 3), (COVER_W - 3, COVER_H - 3)):
            px = img.getpixel(xy)
            self.assertFalse(all(c > 240 for c in px[:3]), xy)
        self.assertNotIn("blank_white_area", qa["findings"])
        self.assertNotIn("not_full_bleed", qa["findings"])

    def test_23_preview_pdf_uses_the_same_cover_asset(self):
        pid, data = self._project(
            title="Field Guide", subtitle="Practical methods for field teams", author="Ada West"
        )
        data = attach_upload(data, _png(), filename="ok.png", license_note="Owned.", project_id=pid, owned=True)
        passing = [lid for lid, row in data["cover_design"]["variants"].items() if row["quality"]["pass"]]
        self.assertTrue(passing)
        data = select_layout(data, passing[0], project_id=pid)
        chosen = data["cover_design"]["variants"][passing[0]]
        pdf = open(chosen["pdf_path"], "rb").read()
        self.assertEqual(hashlib.sha256(pdf).hexdigest(), data["cover_design"]["cover_digest"])
        self.assertEqual(open(data["cover_design"]["local_cover_pdf"], "rb").read(), pdf)
        self.assertEqual(open(chosen["png_path"], "rb").read(), open(data["cover_design"]["image_path"], "rb").read())

    def test_24_draft_approved_locked_projects_not_mutated_by_engine(self):
        before_2472 = hashlib.sha256(
            str(database.get_project(2472)["data"].get("content") or "").encode("utf-8")
        ).hexdigest()
        live_4249 = database.get_project(4249)
        before_ms = manuscript_digest(live_4249["data"]) if live_4249 else None
        before_sha = None
        if live_4249:
            src = ((live_4249["data"].get("cover_design") or {}).get("source") or {})
            before_sha = src.get("sha256")
        pid, data = self._project(title="Isolated", subtitle="Only this project", author="Pat")
        attach_upload(data, _png(), filename="ok.png", license_note="Owned.", project_id=pid, owned=True)
        after_2472 = hashlib.sha256(
            str(database.get_project(2472)["data"].get("content") or "").encode("utf-8")
        ).hexdigest()
        self.assertEqual(after_2472, before_2472)
        self.assertEqual(after_2472, FROZEN_2472_SHA256)
        if before_ms is not None:
            after = database.get_project(4249)["data"]
            self.assertEqual(manuscript_digest(after), before_ms)
            self.assertEqual(((after.get("cover_design") or {}).get("source") or {}).get("sha256"), before_sha)


    def test_25_text_may_sit_on_clothing_not_full_body(self):
        photo = Image.new("RGB", (1600, 2200), (16, 18, 28))
        draw = ImageDraw.Draw(photo)
        draw.ellipse((680, 180, 1080, 680), fill=(198, 148, 118))
        draw.rectangle((720, 680, 1040, 2050), fill=(70, 92, 78))
        ident = _ident(title="Field Notes", subtitle="A short subtitle", author="Ada West")
        img, qa = render_layout_with_qa(photo, "printed_moment", ident, default_editor())
        self.assertEqual(img.size, (COVER_W, COVER_H))
        self.assertTrue(qa["pass"], qa.get("findings"))
        self.assertNotIn("subject_overlap", qa.get("findings") or [])

    def test_26_automatic_recovery_finds_passing_cover(self):
        photo = Image.new("RGB", (1600, 2200), (30, 38, 52))
        draw = ImageDraw.Draw(photo)
        draw.rounded_rectangle((860, 380, 1540, 1760), 36, fill=(16, 16, 20))
        draw.ellipse((940, 720, 1460, 1280), fill=(42, 44, 50))
        buf = io.BytesIO()
        photo.save(buf, format="PNG")
        pid, data = self._project(title="Field Guide", subtitle="Practical methods", author="Ada West")
        data = attach_upload(
            data, buf.getvalue(), filename="camera.png", license_note="Owned.", project_id=pid, owned=True
        )
        public = photo_cover_public_fields(data, project_id=pid)
        self.assertGreater(public["passing_count"], 0, public.get("failed_variants"))
        self.assertEqual(public["workflow_step"], "choose_cover")
        self.assertFalse(public["no_safe_cover"])
        self.assertFalse(public["approvable"])
        self.assertIn("Choose the cover you like.", public["user_status"])
        img, qa, _used, _rec = render_layout_with_recovery(
            photo, "full_bleed_editorial", _ident(), default_editor()
        )
        self.assertTrue(qa["pass"], qa.get("findings"))
        self.assertEqual(img.size, (COVER_W, COVER_H))

    def test_27_zero_pass_uses_choose_another_photo_status(self):
        pid, data = self._project(
            title="Supercalifragilisticexpialidociousantidisestablishmentarianism",
            subtitle="Ok",
            author="A",
        )
        data = attach_upload(data, _png(), filename="ok.png", license_note="Owned.", project_id=pid, owned=True)
        public = photo_cover_public_fields(data, project_id=pid)
        self.assertEqual(public["passing_count"], 0)
        self.assertEqual(public["workflow_step"], "choose_another_photo")
        self.assertEqual(public["choose_another_photo_message"], NO_SAFE_COVER_MESSAGE)
        self.assertFalse(public["approvable"])
        with self.assertRaises(PhotoCoverError):
            select_layout(data, "full_bleed_editorial", project_id=pid)


def _boxes_overlap_local(a, b, pad=8):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return not (ax1 + pad <= bx0 or bx1 + pad <= ax0 or ay1 + pad <= by0 or by1 + pad <= ay0)


if __name__ == "__main__":
    unittest.main()
