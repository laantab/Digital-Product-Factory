"""A book title with a dash of its own must still get a cover.

Real titles are written like "Container Gardening - A Beginner's Guide". The
dash arrives as a token by itself, and the cover's wording check glued the next
word straight onto it -- "- A" became "-A" -- so the check found the wording
rewritten and refused every layout. The customer was told "That cover is not
available. Please choose another," which blamed a photograph that was fine.
"""
import pytest



@pytest.mark.parametrize(
    "lines, expected",
    [
        (["Container Gardening -", "A Beginner's Guide"], "Container Gardening - A Beginner's Guide"),
        (["System Test", "- Six Template Studio"], "System Test - Six Template Studio"),
        (["Grow Food -", "Anywhere"], "Grow Food - Anywhere"),
        (["A -- B"], "A -- B"),
        (["Budget - 2026 -", "Second Edition"], "Budget - 2026 - Second Edition"),
    ],
)
def test_a_dash_of_its_own_keeps_its_spaces(lines, expected):
    from services.ebook_photo_cover import _join_wrapped

    assert _join_wrapped(lines) == expected


@pytest.mark.parametrize(
    "lines, expected",
    [
        (["Dye-", "sublimation Printing"], "Dye-sublimation Printing"),
        (["Self-", "published Authors"], "Self-published Authors"),
        (["Step-by-", "step Setup"], "Step-by-step Setup"),
    ],
)
def test_a_word_broken_across_lines_is_still_put_back_together(lines, expected):
    from services.ebook_photo_cover import _join_wrapped

    assert _join_wrapped(lines) == expected


def test_the_rule_is_about_a_letter_in_front_of_the_hyphen():
    from services.ebook_photo_cover import _continues_a_word

    assert _continues_a_word("dye-") is True
    assert _continues_a_word("2026-") is True
    assert _continues_a_word("-") is False
    assert _continues_a_word("--") is False
    assert _continues_a_word("word") is False


def test_glue_and_join_agree():
    from services.ebook_photo_cover import _glue_tokens, _join_wrapped

    parts = ["Container", "Gardening", "-", "A", "Beginner's", "Guide"]
    assert _glue_tokens(parts) == _join_wrapped([" ".join(parts)])


@pytest.mark.parametrize(
    "title",
    [
        "Container Gardening - A Beginner's Guide",
        "Container Gardening for Beginners - Grow Food",
        "Budget Meals - Week One",
    ],
)
def test_a_dashed_title_gets_covers_a_customer_can_choose(title, tmp_path):
    """End to end: all three layouts must render and pass their own quality check.

    Before the fix every layout failed with identity_text_rewritten, and
    select_layout told the customer the photograph was unusable.
    """
    from services.ebook_photo_cover import LAYOUT_IDS, attach_licensed

    data = {
        "title": title,
        "subtitle": "Grow food in small spaces",
        "author": "A Writer",
        "package_id": f"dash_cover_{abs(hash(title)) % 10**8}",
    }
    data = attach_licensed(data, "event_reception_night", project_id=None)
    variants = data["cover_design"]["variants"]
    assert set(variants) == set(LAYOUT_IDS)
    refused = {
        lid: (v.get("quality") or {}).get("findings")
        for lid, v in variants.items()
        if not (v.get("quality") or {}).get("pass")
    }
    assert not refused, f"{title}: layouts refused: {refused}"
    for lid, v in variants.items():
        assert data["cover_design"]["title"] == title, f"{lid}: cover title is {data['cover_design']['title']!r}"
