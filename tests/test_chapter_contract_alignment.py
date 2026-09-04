"""Generator/validator contract alignment.

Two defects are covered:

1. The writer received only a minimum word count, so a compliant model wrote to
   the floor while the book contract allowed far more. A target derived from the
   book's own range is now supplied.

2. parse_chapter_response's no-heading fallback returned a chapter with no
   tables, making MISSING_REQUIRED_TABLE unsatisfiable no matter what the model
   wrote. The parser was the defect; the validator is unchanged.

No AI call of any kind is made here.
"""
from __future__ import annotations

import pytest

from services.ebook_manuscript_engine import (
    CHAPTER_TARGET_BAND,
    ChapterContract,
    chapter_contract_prompt,
    chapter_target_words,
    extract_markdown_tables,
    parse_chapter_response,
)

TABLE = (
    "| Container | Holds cold |\n"
    "| --- | --- |\n"
    "| Insulated tote | Full shift |\n"
    "| Paper bag | Not at all |\n"
)


# ------------------------------------------------- target calculation ---


def test_generic_book_target_matches_the_contract_midpoint():
    """4000-12000 over 9 chapters -> midpoint 8000 -> ~890 per chapter."""
    assert chapter_target_words(4000, 12000, 9) == 890


def test_catalog_book_gets_a_larger_target():
    assert chapter_target_words(12000, 16000, 9) == 1560


def test_target_scales_with_chapter_count():
    """Same book, more chapters -> smaller per-chapter target."""
    assert chapter_target_words(4000, 12000, 4) > chapter_target_words(4000, 12000, 12)


def test_target_is_zero_when_no_range_or_no_chapters():
    assert chapter_target_words(0, 0, 9) == 0
    assert chapter_target_words(4000, 12000, 0) == 0


def test_reversed_range_is_tolerated():
    assert chapter_target_words(12000, 4000, 9) == chapter_target_words(4000, 12000, 9)


def test_target_never_derived_from_the_maximum_alone():
    """The target describes a solid book, not the largest one allowed."""
    midpoint_based = chapter_target_words(4000, 12000, 9)
    max_based = 12000 // 9
    assert midpoint_based < max_based


# ------------------------------------------------------ prompt text ---


def _safe_prompt(contract) -> str:
    from services.ebook_manuscript_engine import BookContract

    book = BookContract(
        title="T", subtitle="S", author="A", audience="nurses",
        primary_outcome="outcome", approved_outline=[], research_brief="",
        citations=[], editorial_rules=[], chapters=[contract],
    )
    return chapter_contract_prompt(book, contract)


def test_prompt_states_both_minimum_and_target():
    text = _safe_prompt(
        ChapterContract(order=1, title="Chapter One", purpose="p",
                        min_useful_words=500, target_words=890)
    )
    assert "MINIMUM USEFUL DEPTH: 500" in text
    assert "TARGET DEPTH" in text
    assert f"{890 - CHAPTER_TARGET_BAND}-{890 + CHAPTER_TARGET_BAND}" in text


def test_prompt_forbids_padding_to_reach_the_target():
    text = _safe_prompt(
        ChapterContract(order=1, title="C", purpose="p", min_useful_words=500, target_words=890)
    )
    low = text.lower()
    assert "do not add filler" in low
    assert "padding" in low


def test_prompt_omits_target_when_none_supplied():
    """Unchanged behaviour for contracts built without a target."""
    text = _safe_prompt(ChapterContract(order=1, title="C", purpose="p", min_useful_words=500))
    assert "MINIMUM USEFUL DEPTH: 500" in text
    assert "TARGET DEPTH" not in text


def test_required_table_prompt_specifies_real_markdown_format():
    text = _safe_prompt(
        ChapterContract(order=1, title="C", purpose="p", required_table="chapter-comparison")
    )
    assert "chapter-comparison" in text
    assert "| --- |" in text, "the accepted separator-row format must be shown"
    low = text.lower()
    assert "prose" in low and "does not satisfy" in low


# --------------------------------------------- parser table equivalence ---


def test_table_survives_parsing_without_a_chapter_heading():
    """The core parser defect."""
    contract = ChapterContract(order=4, title="Chapter Four", purpose="compare options")
    body_only = f"Some prose about containers.\n\n{TABLE}\nMore prose.\n"
    parsed = parse_chapter_response(body_only, contract)
    assert parsed.tables, "a valid Markdown table must not vanish without a heading"
    assert "|" in parsed.body


def test_table_parsing_is_equivalent_with_and_without_heading():
    contract = ChapterContract(order=4, title="Chapter Four", purpose="compare options")
    inner = f"Some prose about containers.\n\n{TABLE}\nMore prose.\n"

    without = parse_chapter_response(inner, contract)
    with_heading = parse_chapter_response(f"## Chapter Four\n\n{inner}", contract)

    assert len(without.tables) == len(with_heading.tables) == 1
    assert without.tables[0].strip() == with_heading.tables[0].strip()


def test_fallback_populates_deliverables_identically_to_the_heading_path():
    """Whatever the heading path detects, the fallback must detect too.

    This asserts equivalence rather than a particular classification: how
    extract_list_blocks groups adjacent numbered and bulleted lists is existing
    behaviour and deliberately not changed here.
    """
    contract = ChapterContract(order=2, title="Chapter Two", purpose="steps")
    inner = (
        "Intro prose.\n\n"
        "1. First step\n2. Second step\n3. Third step\n\n"
        "- bullet one\n- bullet two\n\n"
        "For example, consider a night shift.\n\n"
        f"{TABLE}"
    )

    without = parse_chapter_response(inner, contract)
    with_heading = parse_chapter_response(f"## Chapter Two\n\n{inner}", contract)

    assert without.tables == with_heading.tables
    assert without.workflows == with_heading.workflows
    assert without.checklists == with_heading.checklists
    assert without.examples == with_heading.examples
    # And the deliverables are genuinely found, not merely equal-and-empty.
    assert without.tables
    assert without.workflows
    assert without.examples


def test_extract_markdown_tables_ignores_prose_pipes():
    """A stray pipe character is not a table."""
    assert extract_markdown_tables("a | b but no separator row") == []


# ------------------------------------------- repair prompt specificity ---


def test_missing_table_repair_instruction_names_the_format():
    from services.ebook_manuscript_engine import format_unresolved_findings_for_prompt

    out = " ".join(format_unresolved_findings_for_prompt(
        ["MISSING_REQUIRED_TABLE: Missing required table: chapter-comparison"]
    ))
    assert "| --- |" in out, "repair must state the accepted Markdown format"
    assert "prose" in out.lower()


def test_thin_chapter_repair_instruction_forbids_padding():
    from services.ebook_manuscript_engine import format_unresolved_findings_for_prompt

    out = " ".join(format_unresolved_findings_for_prompt(["THIN_CHAPTER: 452 useful words"]))
    low = out.lower()
    assert "expand" in low
    assert "filler" in low or "padding" in low


def test_purpose_misalign_repair_instruction_points_at_the_purpose():
    from services.ebook_manuscript_engine import format_unresolved_findings_for_prompt

    out = " ".join(format_unresolved_findings_for_prompt(["PURPOSE_MISALIGN: does not cover purpose"]))
    assert "purpose" in out.lower()


# ------------------------------------------------ purpose contract ---

DENSE_PURPOSE = (
    "Help readers translate the one-meal-two-snacks framework into actual "
    "containers, portions, and packable combinations that fit a work bag."
)


def test_purpose_rule_is_unchanged():
    """The pass/fail rule must be identical -- only the messaging improved."""
    from services.ebook_manuscript_engine import purpose_hit_threshold, purpose_keywords

    toks = purpose_keywords(DENSE_PURPOSE)
    assert "translate" in toks and "packable" in toks
    assert "about" not in toks, "stopwords must still be excluded"
    assert purpose_hit_threshold(toks) == max(2, min(4, len(toks) // 4))


def test_prompt_lists_the_exact_keywords_the_validator_checks():
    from services.ebook_manuscript_engine import PURPOSE_KEYWORDS_CHECKED, purpose_keywords

    text = _safe_prompt(ChapterContract(order=3, title="C", purpose=DENSE_PURPOSE))
    for kw in purpose_keywords(DENSE_PURPOSE)[:PURPOSE_KEYWORDS_CHECKED]:
        assert kw in text, f"writer must be told the validator checks {kw!r}"
    assert "MUST ENGAGE" in text


def test_prompt_forbids_the_generic_opening_that_caused_the_failure():
    text = _safe_prompt(ChapterContract(order=3, title="C", purpose=DENSE_PURPOSE)).lower()
    assert "generic scene-setting" in text


def test_purpose_misalign_finding_names_the_missing_keywords():
    """Automatic repair needs specifics, not 'something was wrong'."""
    from services.ebook_manuscript_engine import BookContract, ParsedChapter, validate_chapter

    contract = ChapterContract(order=3, title="Ch", purpose=DENSE_PURPOSE, min_useful_words=5)
    book = BookContract(
        title="T", subtitle="S", author="A", audience="x", primary_outcome="y",
        approved_outline=[], research_brief="", citations=[], editorial_rules=[],
        chapters=[contract],
    )
    body = "Generic prose about a long day that never engages the subject at all."
    findings = validate_chapter(ParsedChapter(order=3, title="Ch", body=body), contract, book=book)
    misalign = [f for f in findings if f.code == "PURPOSE_MISALIGN"]
    assert misalign, "this body should misalign"
    assert "translate" in misalign[0].message
    assert "packable" in misalign[0].message


def test_repair_instruction_carries_the_missing_keywords_through():
    from services.ebook_manuscript_engine import format_unresolved_findings_for_prompt

    finding = (
        "PURPOSE_MISALIGN: Chapter body does not cover the approved purpose for "
        "this title. Purpose keywords not addressed: translate, portions, packable"
    )
    out = " ".join(format_unresolved_findings_for_prompt([finding]))
    assert "translate" in out and "portions" in out and "packable" in out
    assert "paraphrasing" in out.lower()


def test_repair_instruction_still_works_without_keyword_detail():
    """Older/other-shaped findings must not break the repair path."""
    from services.ebook_manuscript_engine import format_unresolved_findings_for_prompt

    out = " ".join(format_unresolved_findings_for_prompt(["PURPOSE_MISALIGN: generic"]))
    assert "purpose" in out.lower()
