"""No two chapters may share a photograph, and graphics must not print markup.

ROOT CAUSE THIS GUARDS
----------------------
A real cookbook shipped with chapters 5, 6 and 7 carrying the same image, byte
for byte, all three marked PASS. Neighbouring chapters have near-identical
briefs, so stock search returned the same top result for each, and the
duplicate check that existed only fired when re-hashing the file on disk
happened to agree with the stored hash.

Rejecting duplicates after the fact was not enough either: the retry chose the
same top result again, so the duplicate simply moved. Images already used are
now excluded from every later search, and a final pass over the whole book
refuses a repeat by content hash, provider asset id, or source URL.

Two rendering defects are covered here too, both visible in a finished book:
a totals row written as **Total** printed its asterisks, and a five-column
table silently lost its last column.

No external call is made by any test here.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("FACTORY_TEST_MODE", "1")

from services.ebook_visual_match import (  # noqa: E402
    MATCH_PASS,
    MATCH_REJECT,
    enforce_unique_photographs,
)


def _photo(visual_id: str, *, sha: str = "", photo_id: str = "", url: str = ""):
    return {
        "type": "photo",
        "visual_id": visual_id,
        "sha256": sha,
        "photo_id": photo_id,
        "page_url": url,
        "match_status": MATCH_PASS,
        "approved": True,
    }


def _plan(*aids):
    return {
        "chapters": [
            {"chapter": f"Chapter {i}", "aids": [aid]}
            for i, aid in enumerate(aids, 1)
        ]
    }


def _statuses(plan):
    return [
        aid["match_status"]
        for ch in plan["chapters"]
        for aid in ch["aids"]
    ]


# ------------------------------------------------------------ uniqueness ---


def test_the_same_content_hash_is_rejected_after_the_first_use():
    plan = enforce_unique_photographs(_plan(
        _photo("a", sha="aaa"), _photo("b", sha="aaa"), _photo("c", sha="aaa"),
    ))
    assert _statuses(plan) == [MATCH_PASS, MATCH_REJECT, MATCH_REJECT]


def test_the_same_provider_asset_id_is_rejected():
    plan = enforce_unique_photographs(_plan(
        _photo("a", photo_id="55"), _photo("b", photo_id="55"),
    ))
    assert _statuses(plan) == [MATCH_PASS, MATCH_REJECT]


def test_the_same_source_url_is_rejected():
    plan = enforce_unique_photographs(_plan(
        _photo("a", url="https://x.test/p/1"),
        _photo("b", url="https://X.test/p/1"),
    ))
    assert _statuses(plan) == [MATCH_PASS, MATCH_REJECT]


def test_distinct_photographs_are_all_kept():
    plan = enforce_unique_photographs(_plan(
        _photo("a", sha="aaa", photo_id="1", url="https://x.test/1"),
        _photo("b", sha="bbb", photo_id="2", url="https://x.test/2"),
        _photo("c", sha="ccc", photo_id="3", url="https://x.test/3"),
    ))
    assert _statuses(plan) == [MATCH_PASS] * 3


def test_a_duplicate_records_why_and_never_stays_approved():
    plan = enforce_unique_photographs(_plan(
        _photo("a", sha="aaa"), _photo("b", sha="aaa", photo_id="77"),
    ))
    second = plan["chapters"][1]["aids"][0]
    assert second["approved"] is False
    assert second["internally_ready"] is False
    assert "already used" in second["rejection_reason"].lower()
    assert second["duplicate_of"] == "Chapter 1"
    assert "77" in second["rejected_photo_ids"], "the repeat must not be offered again"


def test_local_graphics_are_not_treated_as_duplicates():
    """Two checklists are not two copies of one photograph."""
    plan = {
        "chapters": [
            {"chapter": "One", "aids": [{"type": "checklist", "visual_id": "a"}]},
            {"chapter": "Two", "aids": [{"type": "checklist", "visual_id": "b"}]},
        ]
    }
    out = enforce_unique_photographs(plan)
    for ch in out["chapters"]:
        assert "match_status" not in ch["aids"][0]


def test_the_uniqueness_pass_runs_as_part_of_stamping():
    src = (ROOT / "services" / "ebook_visual_match.py").read_text(encoding="utf-8")
    start = src.index("def stamp_plan_photo_matches")
    body = src[start:src.index("\ndef ", start + 10)]
    assert "enforce_unique_photographs(plan)" in body


def test_acquisition_excludes_images_already_used():
    """Rejecting afterwards only moves the duplicate; the search must exclude."""
    src = (ROOT / "services" / "ebook_factory_pipeline.py").read_text(encoding="utf-8")
    start = src.index("def fill_plan_photos_automatic")
    body = src[start:src.index("\ndef ", start + 10)]
    assert "used_photo_ids" in body
    assert "rejected_photo_ids" in body
    assert body.index("used_photo_ids") < body.index("fill_photo_aid_automatic")


# ------------------------------------------------------------- rendering ---


def test_markdown_emphasis_never_reaches_a_drawn_cell():
    from services.ebook_visual_pipeline import _plain_cell

    assert _plain_cell("**Total**") == "Total"
    assert _plain_cell("**3,000**") == "3,000"
    assert _plain_cell("*Lunch*") == "Lunch"
    assert _plain_cell("`code`") == "code"
    assert _plain_cell("Breakfast") == "Breakfast"
    assert _plain_cell(None) == ""


def test_a_five_column_table_keeps_every_column():
    from services.ebook_visual_pipeline import _COMPARISON_MAX_COLS, _render_comparison

    assert _COMPARISON_MAX_COLS >= 5, "a five-column nutrition table must survive"
    aid = {
        "type": "comparison",
        "title": "Totals",
        "table": {
            "headers": ["**Meal Type**", "Calories", "Protein", "Carbs", "Fat"],
            "rows": [["Breakfast", "650", "43g", "65g", "22g"],
                     ["**Total**", "**3,000**", "212g", "245g", "96g"]],
        },
    }
    image = _render_comparison(aid)
    assert image.width > 0 and image.height > 0


def test_a_card_label_is_never_cut_in_the_middle_of_a_word():
    """Two limits disagreed: the trimmer stopped at a word, the renderer did not.

    A shipped chapter graphic read "This structure not only reduces decision
    fatigue but also helps you buil".
    """
    from services.ebook_visual_pipeline import _CARD_LABEL_LIMIT, _LABEL_LIMIT, _short_items

    assert _CARD_LABEL_LIMIT >= _LABEL_LIMIT, "the renderer must not re-cut a trimmed label"

    long_line = (
        "This structure not only reduces decision fatigue but also helps you "
        "build a habit that fits into your sedentary workweek without effort"
    )
    (out,) = _short_items([long_line], 1)
    assert len(out) <= _CARD_LABEL_LIMIT + 1  # the ellipsis
    assert out.endswith("…")
    tail = out[:-1].rstrip().split()[-1]
    assert long_line.split().count(tail) or tail in long_line.split(), (
        f"label ends mid-word: ...{out[-30:]!r}"
    )


def test_a_checklist_badge_does_not_depend_on_a_font_glyph():
    """The badge printed an empty box on the machine that built a real book."""
    src = (ROOT / "services" / "ebook_visual_pipeline.py").read_text(encoding="utf-8")
    start = src.index("def _render_steps")
    body = src[start:src.index("\ndef ", start + 10)]
    assert "☐" not in body and "✓" not in body, "a drawn mark cannot go missing; a glyph can"
    assert "_draw_tick" in body


def test_a_checklist_renders_with_its_marks():
    from services.ebook_visual_pipeline import _render_steps

    aid = {"type": "checklist", "title": "Before you leave", "items": ["One", "Two"]}
    image = _render_steps(aid, kind="checklist")
    assert image.width > 0 and image.height > 0


def test_short_rows_are_padded_so_columns_stay_aligned():
    from services.ebook_visual_pipeline import _render_comparison

    aid = {
        "type": "comparison",
        "title": "Ragged",
        "table": {"headers": ["A", "B", "C"], "rows": [["1", "2"], ["3"]]},
    }
    assert _render_comparison(aid) is not None
