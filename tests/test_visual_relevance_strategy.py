"""Photographs must be judged by their pixels, and abstract chapters must not
be forced into stock photography.

ROOT CAUSE THIS GUARDS
----------------------
Two defects shipped books full of stock filler.

1. score_photo_against_brief decided from the candidate's own metadata -- alt
   text, tags, filename, page URL. Metadata is written by whoever uploaded the
   image, so burnt matchsticks arranged to spell MIND are tagged "mind",
   satisfied a brief requiring the subject "mind", and were marked PASS. A real
   nine-chapter book was assembled from chalk tally marks, a typewriter
   photographed with text on the page, a woman throwing a book, two clocks
   matched to the word "minute", and that matchstick word art. Six of eight
   photographs were unusable and the visuals gate approved them.

2. The planner only produced a local graphic when the chapter contained a
   markdown table, numbered list or bullet list. A reflective, advice-led
   chapter written as prose fell through to a photograph -- and stock search
   answers an abstract heading with a clock or a signpost.

Nothing here is specific to one book, one topic or one chapter title.
No external call is made by any test.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("FACTORY_TEST_MODE", "1")

from services.ebook_photo_content import (  # noqa: E402
    cliche_rejection_reason,
    describe_photo_content,
    detail_spread,
    topic_supported,
)

TOPIC = "mindfulness meditation for beginners"
BODY = "Sit down, settle your posture and let your breathing find its rhythm."


# --------------------------------------------------------------- fixtures ---


def _flat_graphic(tmp_path: Path) -> str:
    """A word-art style image: one flat ground, a few marks in the middle."""
    img = Image.new("RGB", (1200, 800), (232, 214, 200))
    draw = ImageDraw.Draw(img)
    for i in range(4):
        x = 380 + i * 90
        draw.rectangle([x, 360, x + 14, 440], fill=(60, 40, 30))
    path = tmp_path / "flat.png"
    img.save(path)
    return str(path)


def _photographic_scene(tmp_path: Path) -> str:
    """Detail spread across the whole frame, as a photograph has."""
    import random

    rng = random.Random(7)
    img = Image.new("RGB", (1200, 800))
    px = img.load()
    for y in range(800):
        for x in range(1200):
            px[x, y] = (
                (x * 7 + y * 3 + rng.randint(0, 90)) % 256,
                (y * 5 + rng.randint(0, 90)) % 256,
                (x * 3 + rng.randint(0, 90)) % 256,
            )
    path = tmp_path / "scene.png"
    img.save(path)
    return str(path)


# ------------------------------------------------------- pixel inspection ---


def test_flatness_is_recorded_but_never_rejects_on_its_own(tmp_path):
    """Flatness is suggestive, not decisive.

    A legitimate photograph can be a product on a seamless white sweep, and a
    small or synthetic image reads as flat too. Rejecting on flatness alone
    threw out valid photographs -- and, worse, pushed the pipeline toward the
    paid generator. It is recorded as a weak signal instead.
    """
    report = describe_photo_content(_flat_graphic(tmp_path))
    assert report["inspected"] is True
    assert report["weak_findings"], report
    assert any("flat" in f or "detail" in f for f in report["weak_findings"])
    assert report["findings"] == [], "flatness must not be a hard rejection"
    assert report["ok"] is True


def test_a_photographed_scene_passes_inspection(tmp_path):
    report = describe_photo_content(_photographic_scene(tmp_path))
    assert report["inspected"] is True
    assert report["ok"] is True, report["findings"]


def test_detail_spread_separates_graphics_from_photographs(tmp_path):
    assert detail_spread(_flat_graphic(tmp_path)) < detail_spread(
        _photographic_scene(tmp_path)
    )


def test_an_unreadable_image_is_never_treated_as_fine():
    report = describe_photo_content("/no/such/file.png")
    assert report["inspected"] is False
    assert report["ok"] is False


# --------------------------------------------------- metadata may reject ----


def test_word_art_is_rejected():
    for alt in (
        "Scrabble tiles spelling the word FEEL",
        "Burnt matchsticks arranged to spell MIND on pink paper",
        "Motivational quote written on a chalkboard",
        "Vintage typewriter with a page of typed text",
        "Wooden letters spelling calm on a table",
    ):
        assert cliche_rejection_reason(alt, book_topic=TOPIC), alt


def test_a_clock_matched_to_the_word_minute_is_rejected():
    for alt in ("Round analog wall clock", "Black alarm clock on a table",
                "Gold pocket watch lying on a book", "Sand timer hourglass"):
        assert cliche_rejection_reason(alt, book_topic=TOPIC), alt


def test_a_clock_is_allowed_when_the_book_is_about_time():
    assert not cliche_rejection_reason(
        "Black alarm clock on a desk", book_topic="time management for managers"
    )


def test_symbolic_cliches_are_rejected():
    assert cliche_rejection_reason("Tally marks on a blackboard", book_topic=TOPIC)
    assert cliche_rejection_reason("Conceptual light bulb idea", book_topic=TOPIC)


def test_a_real_subject_photograph_is_not_rejected():
    for alt in (
        "Woman meditating on a bench in a park",
        "Businesswoman meditating on a hotel room floor",
    ):
        assert not cliche_rejection_reason(alt, book_topic=TOPIC, chapter_body=BODY), alt


# ------------------------------------------------ topic, not the heading ----


def test_the_book_subject_must_be_present_not_just_the_heading():
    assert topic_supported("Woman meditating on a bench", book_topic=TOPIC, chapter_body=BODY)
    # Matches the heading word "feel"/"hard" but nothing about the book.
    assert not topic_supported(
        "Woman in gothic makeup throwing a black book", book_topic=TOPIC, chapter_body=BODY
    )


def test_word_forms_of_the_same_subject_count_as_the_subject():
    assert topic_supported("A meditating woman", book_topic="meditation practice")
    assert topic_supported("Gardening tools in soil", book_topic="container gardener guide")


# ----------------------------------------------- the strictness gate wiring --


def test_metadata_alone_can_never_grant_a_pass():
    """The whole defect in one assertion."""
    from services.ebook_visual_match import MATCH_PASS, build_visual_brief, score_photo_against_brief

    aid = {"type": "photo", "visual_id": "v1", "title": "chapter scene",
           "caption": "a mindfulness practice", "chapter": "Practice"}
    brief = build_visual_brief(aid, chapter="Practice", title="Mindfulness", topic=TOPIC)
    report = score_photo_against_brief(
        brief,
        alt="mindfulness meditation practice calm breathing",
        page_url="https://example.test/photo/1",
        filename="mindfulness-meditation.jpg",
        book_topic=TOPIC,
        chapter_body=BODY,
    )
    assert report.status != MATCH_PASS, (
        "a candidate with no inspected pixels must never reach PASS"
    )


def test_a_cliche_is_rejected_even_when_the_metadata_fits_the_brief(tmp_path):
    from services.ebook_visual_match import MATCH_REJECT, build_visual_brief, score_photo_against_brief

    aid = {"type": "photo", "visual_id": "v1", "title": "chapter scene",
           "caption": "five minute practice", "chapter": "Your First 5-Minute Practices"}
    brief = build_visual_brief(aid, chapter="Your First 5-Minute Practices",
                               title="5-Minute Mindfulness", topic=TOPIC)
    report = score_photo_against_brief(
        brief,
        alt="Round analog wall clock showing five minutes",
        image_path=_photographic_scene(tmp_path),
        book_topic=TOPIC,
        chapter_body=BODY,
    )
    assert report.status == MATCH_REJECT, report.status
    assert "timekeeping" in (report.rejection_reason or "").lower()


def test_the_gate_only_ever_makes_the_verdict_stricter():
    """It must be impossible for the new gate to promote a rejection."""
    src = (ROOT / "services" / "ebook_visual_match.py").read_text(encoding="utf-8")
    gate = src[src.index("# ---------------------------------------------------------------- STRICT"):]
    gate = gate[: gate.index("return MatchReport(")]
    # Every assignment of MATCH_PASS inside the gate would be a promotion.
    assert "status = MATCH_PASS" not in gate, "the strictness gate must never grant a pass"
    assert "MATCH_REJECT" in gate and "MATCH_NEEDS_REVIEW" in gate


# ------------------------------------------- abstract chapters go local ------


PROSE_INSTRUCTIONS = (
    "A short practice is easy to keep. Sit down and settle your posture. "
    "Close your eyes gently and bring your attention to your breath. "
    "Inhale slowly through your nose for four seconds. "
    "Hold for four seconds, and repeat."
)
PROSE_ADVICE = (
    "Some sessions feel restless and unrewarding, and that is expected. "
    "Difficulty is part of the beginner experience, not a sign of failure. "
    "The practice is about noticing when attention wanders and returning to it. "
    "Restlessness means the mind is awake, rather than that the method is wrong. "
    "The goal is not a silent mind, but a kinder response to a busy one. "
    "Consistency helps far more than the length of any single session."
)


def test_a_prose_chapter_of_instructions_becomes_a_practice_sequence():
    from services.ebook_visual_pipeline import derive_local_aid_from_prose

    aid = derive_local_aid_from_prose(1, "Your First Practices", PROSE_INSTRUCTIONS)
    assert aid and aid["type"] == "workflow", aid
    assert len(aid["items"]) >= 3
    for item in aid["items"]:
        assert item.rstrip("…") in PROSE_INSTRUCTIONS or item in PROSE_INSTRUCTIONS, item


def test_a_prose_chapter_of_advice_becomes_key_points():
    from services.ebook_visual_pipeline import derive_local_aid_from_prose

    aid = derive_local_aid_from_prose(2, "When It Feels Hard", PROSE_ADVICE)
    assert aid and aid["type"] == "checklist", aid
    assert len(aid["items"]) >= 3


def test_derived_items_never_invent_content():
    """Every label is a span of the chapter, trimmed only at a word boundary."""
    from services.ebook_visual_pipeline import derive_local_aid_from_prose

    for body in (PROSE_INSTRUCTIONS, PROSE_ADVICE):
        aid = derive_local_aid_from_prose(1, "Chapter", body)
        assert aid
        for item in aid["items"]:
            head = item.rstrip("…").rstrip(" ,;:")
            assert head in body, f"item is not from the manuscript: {item!r}"


def test_derived_items_are_short_enough_not_to_be_chopped():
    from services.ebook_visual_pipeline import derive_local_aid_from_prose

    for body in (PROSE_INSTRUCTIONS, PROSE_ADVICE):
        aid = derive_local_aid_from_prose(1, "Chapter", body)
        for item in aid["items"]:
            assert len(item) <= 80, item


def test_narrative_scene_setting_is_not_a_key_point():
    from services.ebook_visual_pipeline import derive_local_aid_from_prose

    body = (
        "It's 9:15 a.m., and you are standing in line at the shop. "
        "Imagine you are waiting for a bus with nothing to do. "
        "Mindfulness is about noticing when attention wanders and returning it. "
        "Difficulty is part of the beginner experience, not a sign of failure. "
        "The goal is not a silent mind, but a kinder response to a busy one. "
        "Consistency helps far more than the length of any single session."
    )
    aid = derive_local_aid_from_prose(1, "Chapter", body)
    assert aid
    joined = " ".join(aid["items"]).lower()
    assert "9:15" not in joined and "imagine" not in joined, aid["items"]


def test_a_photo_led_subject_still_gets_photographs():
    """Concrete, physical subjects must keep stock photography."""
    from services.ebook_visual_match import is_photo_led_subject

    assert is_photo_led_subject(
        title="Container Gardening for Small Spaces",
        topic="container gardening",
        content="Fill the pot with compost and plant the tomato seedling.",
    )


def test_the_planner_only_derives_local_visuals_for_non_photo_subjects():
    src = (ROOT / "services" / "ebook_visual_pipeline.py").read_text(encoding="utf-8")
    start = src.index("def plan_content_aware_visuals")
    body = src[start:src.index("\ndef ", start + 10)]
    assert "is_photo_led_subject" in body
    assert "derive_local_aid_from_prose" in body
    # The photo branch must still exist for photo-led books.
    assert "include_photographs" in body
