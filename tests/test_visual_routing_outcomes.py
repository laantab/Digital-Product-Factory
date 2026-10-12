"""A rejected photograph must not become a purchase.

ROOT CAUSE THIS GUARDS
----------------------
Every stock failure looked the same to the caller, so "the photograph we found
is a clock matched to the word minute" was handled exactly like "stock has
nothing at all": both fell through to the paid image generator. Making the
matcher stricter therefore made the Factory SPEND MORE, which is the opposite
of the intent.

Acquisition now reports a typed outcome and the caller routes on it. A wrong
picture is answered with a free visual built from the chapter's own text. Paid
generation stays reachable only when stock cannot supply an asset AND no
honest free visual exists AND the owner authorized it AND budget remains --
the guarantee the existing paid-fallback tests were written to protect.

No external call is made by any test here.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("FACTORY_TEST_MODE", "1")

from services.ebook_factory_pipeline import (  # noqa: E402
    LOCAL_VISUAL_UNSUITABLE,
    SEMANTIC_REJECTION,
    STOCK_ACCEPTED,
    STOCK_UNAVAILABLE,
    TECHNICAL_FAILURE,
    _classify_stock_failure,
    _local_visual_for_aid,
)

INSTRUCTIONAL_BODY = (
    "A short practice is easy to keep. Sit down and settle your posture. "
    "Close your eyes gently and bring your attention to your breath. "
    "Inhale slowly through your nose for four seconds. "
    "Hold for four seconds, and repeat."
)


def _aid(**over):
    aid = {
        "type": "photo",
        "visual_id": "v_ch3",
        "title": "chapter scene",
        "caption": "a practice",
        "chapter": "Your First Practices",
        "chapter_index": 3,
        "placement": "after_opening",
    }
    aid.update(over)
    return aid


# ------------------------------------------------------ outcome taxonomy ---


def test_the_five_outcomes_are_distinct():
    values = {
        STOCK_ACCEPTED, SEMANTIC_REJECTION, STOCK_UNAVAILABLE,
        TECHNICAL_FAILURE, LOCAL_VISUAL_UNSUITABLE,
    }
    assert len(values) == 5


def test_a_wrong_picture_is_classified_as_a_semantic_rejection():
    for reason in (
        "image is about words, not the subject (matchstick)",
        "generic timekeeping prop (clock) matched a mention of time",
        "symbolic stock cliché (tally) instead of the chapter's subject",
        "prominent text in the image: MIND",
        "the photograph matches the chapter heading but not the book's subject",
        "missing required subject",
    ):
        assert _classify_stock_failure(reason) == SEMANTIC_REJECTION, reason


def test_no_picture_is_not_a_semantic_rejection():
    for reason in ("", "No matching photograph was found.",
                   "Every Pexels result failed the visual brief."):
        assert _classify_stock_failure(reason) == STOCK_UNAVAILABLE, reason


# --------------------------------------------------- free local visual -----


def test_a_chapter_with_instructions_yields_a_free_local_visual():
    local = _local_visual_for_aid(
        _aid(chapter_body=INSTRUCTIONAL_BODY), chapter="Your First Practices"
    )
    assert local is not None
    assert local["type"] in {"workflow", "checklist"}
    assert local["visual_id"] == "v_ch3", "the slot identity must be preserved"
    assert local["chapter_index"] == 3
    assert local["placement"] == "after_opening"
    assert "photo" not in str(local.get("source") or "")


def test_a_chapter_with_no_usable_text_is_local_visual_unsuitable():
    assert _local_visual_for_aid(_aid(chapter_body=""), chapter="Empty") is None
    assert _local_visual_for_aid(_aid(), chapter="No body") is None
    assert _local_visual_for_aid(_aid(chapter_body="Hello."), chapter="Tiny") is None


# ------------------------------------------------------- routing policy -----


def _routing_source() -> str:
    src = (ROOT / "services" / "ebook_factory_pipeline.py").read_text(encoding="utf-8")
    start = src.index("def fill_photo_aid_automatic")
    return src[start:src.index("\ndef ", start + 10)]


def test_the_free_local_visual_is_tried_before_any_paid_call():
    body = _routing_source()
    local_at = body.index("_local_visual_for_aid")
    ai_at = body.index("fill_photo_aid_with_ai")
    assert local_at < ai_at, "paid generation must come after the free attempt"


def test_paid_generation_still_requires_authorization_and_budget():
    body = _routing_source()
    assert "if not allow_ai:" in body
    assert "visual_ai_authorized(payload, fields)" in body
    # Both guards must sit between the local attempt and the paid call.
    local_at = body.index("_local_visual_for_aid")
    ai_at = body.index("fill_photo_aid_with_ai")
    assert local_at < body.index("if not allow_ai:") < ai_at
    assert local_at < body.index("visual_ai_authorized(payload, fields)") < ai_at


def test_a_successful_local_visual_returns_before_the_paid_branch():
    body = _routing_source()
    segment = body[body.index("_local_visual_for_aid"):body.index("fill_photo_aid_with_ai")]
    assert "return local" in segment, (
        "an honest free visual must end the routing, not fall through to a purchase"
    )


def test_an_accepted_photograph_short_circuits_everything():
    from unittest.mock import patch
    from services import ebook_factory_pipeline as pipeline
    accepted = _aid(match_status='pass')
    with patch.object(pipeline, 'fill_photo_aid_from_pexels', return_value=accepted), \
         patch.object(pipeline, '_photo_already_stored', return_value=True), \
         patch.object(pipeline, '_local_visual_for_aid', side_effect=AssertionError('unnecessary fallback')), \
         patch.object(pipeline, 'fill_photo_aid_with_ai', side_effect=AssertionError('paid call')):
        result = pipeline.fill_photo_aid_automatic(_aid(), package_id='accepted-test', allow_ai=False)
    assert result is accepted


def test_the_paid_safeguards_were_not_deleted():
    src = (ROOT / "services" / "ebook_factory_pipeline.py").read_text(encoding="utf-8")
    for guard in (
        "def visual_ai_authorized",
        "def charge_visual_ai_call",
        "def remaining_visual_budget_usd",
        "def budget_visual_customer_message",
    ):
        assert guard in src, f"paid-call safeguard removed: {guard}"


def test_acquisition_stamps_an_outcome_on_every_path():
    src = (ROOT / "services" / "ebook_factory_pipeline.py").read_text(encoding="utf-8")
    start = src.index("def fill_photo_aid_from_pexels")
    body = src[start:src.index("\ndef _local_visual_for_aid", start)]
    assert body.count("acquisition_outcome") >= 3, (
        "stored, exhausted and errored paths must all report an outcome"
    )
    assert "TECHNICAL_FAILURE" in body
    assert "STOCK_ACCEPTED" in body


def test_uncertain_stock_uses_the_free_chapter_graphic_without_a_paid_call():
    from unittest.mock import patch
    from services import ebook_factory_pipeline as pipeline
    uncertain = _aid(chapter_body=INSTRUCTIONAL_BODY, match_status='needs_review',
                     acquisition_outcome=SEMANTIC_REJECTION)
    with patch.object(pipeline, 'fill_photo_aid_from_pexels', return_value=uncertain), \
         patch.object(pipeline, '_photo_already_stored', return_value=True), \
         patch.object(pipeline, 'fill_photo_aid_with_ai', side_effect=AssertionError('paid call')):
        result = pipeline.fill_photo_aid_automatic(
            _aid(chapter_body=INSTRUCTIONAL_BODY), package_id='uncertain-test',
            chapter='Your First Practices', allow_ai=False)
    assert result['type'] in {'workflow', 'checklist'}
    assert result['visual_id'] == 'v_ch3'


def test_guided_free_replacement_cannot_reach_paid_generation(tmp_path):
    from unittest.mock import patch
    from services import ebook_factory_pipeline as pipeline
    from services.ebook_visual_pipeline import replace_photo_aid
    data = {'visual_plan': {'chapters': [{'chapter': 'Your First Practices',
             'aids': [_aid(chapter_body=INSTRUCTIONAL_BODY)]}]}}
    local = _local_visual_for_aid(data['visual_plan']['chapters'][0]['aids'][0])
    with patch.object(pipeline, 'fill_photo_aid_automatic', return_value=local) as fill, \
         patch('services.ebook_visual_pipeline.EXPORTS_DIR', str(tmp_path)), \
         patch('services.ebook_visual_pipeline.write_visual_contact_sheet'):
        replace_photo_aid(data, 'v_ch3', mode='automatic-free')
    assert fill.call_args.kwargs['allow_ai'] is False
    assert data['visual_plan']['chapters'][0]['aids'][0]['type'] == local['type']
    replaced = data['visual_plan']['chapters'][0]['aids'][0]
    assert Path(replaced['asset_path']).is_file()
    import hashlib
    assert hashlib.sha256(Path(replaced['asset_path']).read_bytes()).hexdigest() == replaced['sha256']
