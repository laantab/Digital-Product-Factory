"""Prose chapters must be searched on their subject, not their heading.

ROOT CAUSE THIS GUARDS
----------------------
chapter_pexels_queries built its ladder from the chapter HEADING whenever the
book named no defining equipment. A heading is rhetoric, not a scene, so for
"5-Minute Mindfulness for Busy Beginners" the searches ran as "minute
practices" and "feels hard" -- and Pexels answered with a gold pocket watch on
a book and Scrabble tiles spelling FEEL. The matcher correctly refused both
(needs_user_review), the visuals stage would not approve, and the whole
photograph search had been spent on words the book is not about.

The ladder now leads with the book's own subject combined with the chapter's
own body text. Equipment-led books are untouched.

No external call is made by any test here: chapter_pexels_queries is pure
string work and no search is performed.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("FACTORY_TEST_MODE", "1")

from services.ebook_pexels import chapter_pexels_queries  # noqa: E402

BOOK_TITLE = "5-Minute Mindfulness for Busy Beginners"
BOOK_TOPIC = "mindfulness meditation for beginners"

CH4 = "Your First 5-Minute Practices"
CH4_BODY = (
    "A five-minute practice is short enough to keep. Sit down, settle your posture, "
    "and let your breathing find its own rhythm. Notice the breath at the nose."
)
CH8 = "When It Feels Hard, You're Still Doing It Right"
CH8_BODY = (
    "Some sittings feel restless and unrewarding. A hard sitting is not a failed "
    "sitting. Meeting difficulty with self-compassion is the practice itself."
)


def _queries(chapter: str, body: str) -> list[str]:
    return chapter_pexels_queries(
        chapter=chapter,
        title=BOOK_TITLE,
        topic=BOOK_TOPIC,
        caption=f"{chapter}: chapter scene",
        body=body,
        audience="busy beginners",
    )


def test_the_first_query_is_anchored_to_the_books_subject():
    for chapter, body in ((CH4, CH4_BODY), (CH8, CH8_BODY)):
        first = _queries(chapter, body)[0]
        assert "mindfulness" in first, (
            f"{chapter!r} led with {first!r}, which is not about the book's subject"
        )


def test_the_heading_alone_is_never_searched_first():
    """These exact phrases returned a pocket watch and Scrabble tiles."""
    assert _queries(CH4, CH4_BODY)[0] != "first 5-minute practices minute"
    assert _queries(CH8, CH8_BODY)[0] != "feels hard still doing right"


def test_the_chapters_own_words_reach_the_search():
    """The body describes the scene; it must contribute to the ladder."""
    ladder = " | ".join(_queries(CH4, CH4_BODY))
    assert any(word in ladder for word in ("practice", "breath", "posture", "short")), ladder
    ladder8 = " | ".join(_queries(CH8, CH8_BODY))
    assert any(word in ladder8 for word in ("sitting", "sittings", "restless", "difficulty")), ladder8


def test_a_bare_topic_search_is_available_as_a_floor():
    for chapter, body in ((CH4, CH4_BODY), (CH8, CH8_BODY)):
        assert "mindfulness meditation" in _queries(chapter, body)


def test_equipment_led_books_are_not_changed():
    """A book with a defining implement keeps it in every tier, first."""
    q = chapter_pexels_queries(
        chapter="Deadlift Form and Technique",
        title="Kettlebell Strength for Beginners",
        topic="kettlebell strength training",
        caption="deadlift demonstration",
        body="Hinge at the hips and keep the spine neutral.",
        audience="beginners",
    )
    assert q[0].startswith("kettlebell"), q
    assert all("kettlebell" in item for item in q[:4]), q


def test_queries_stay_short_and_unique():
    for chapter, body in ((CH4, CH4_BODY), (CH8, CH8_BODY)):
        q = _queries(chapter, body)
        assert q, "the ladder must never be empty"
        assert len(q) == len(set(q)), f"duplicate queries: {q}"
        for item in q:
            assert 0 < len(item.split()) <= 8, f"unusable query {item!r}"


def test_missing_body_still_produces_an_anchored_ladder():
    """An aid with no stored body must not regress to heading-only search."""
    q = _queries(CH4, "")
    assert q and "mindfulness" in q[0], q


def test_the_caller_passes_the_chapter_body_through():
    src = (ROOT / "services" / "ebook_factory_pipeline.py").read_text(encoding="utf-8")
    start = src.index("def fill_photo_aid_from_pexels")
    body = src[start:src.index("\ndef ", start + 10)]
    assert 'body=str(out.get("chapter_body") or "")' in body, (
        "the chapter body must reach the query builder or the fix is inert"
    )
