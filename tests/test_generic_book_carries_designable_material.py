"""A generic ebook must be *required* to carry material the interior needs.

"Container Gardening for Beginners" was written, passed every manuscript
check with zero findings, and then could not be designed:

    Visuals cannot be approved: Only 1 kind(s) of visual across 9: photo.
    A designed interior needs at least 3.

Two gates disagreed. The interior editorial floor demands three distinct
kinds of visual. The generic book contract demanded no structured
material at all: `required_table` / `required_workflow` /
`required_checklist` were set only when the outline's *purpose* text
happened to contain a keyword like "table" or "checklist". Container
Gardening's purposes triggered three tables, the writer produced exactly
three tables and volunteered nothing else, and the interior had nothing
but photographs to work with.

It was never a provider problem. A different book (project 351) cleared
the same floor only because its model volunteered 105 table rows, 6
checkboxes and 30 numbered steps that nothing had asked for. Passing was
luck.

THE LESSON THIS FILE EXISTS TO KEEP
-----------------------------------
A requirement is only real if the thing demanded is the same thing the
validator detects AND the same thing the interior planner can draw. Last
release shipped a check that demanded something no generator could ever
satisfy, and a book burned sixty attempts on it. So these tests assert the
three-way agreement directly: what the contract asks for, what
`validate_chapter` accepts, and what `_choose_aid` turns into a visual.

No AI call of any kind is made here.
"""
from __future__ import annotations

import pytest

from services.ebook_manuscript_engine import (
    GENERIC_CHECKLIST_SPEC,
    GENERIC_WORKFLOW_SPEC,
    _has_checklist,
    _has_workflow,
    build_book_contract,
)
from services.ebook_visual_editorial import review_visual_set
from services.ebook_visual_pipeline import (
    _choose_aid,
    _parse_checkbox_items,
    _parse_workflow,
)

CHECKLIST_BLOCK = (
    "**Before you plant checklist**\n\n"
    "- [ ] Check the pot has drainage holes\n"
    "- [ ] Fill with fresh potting mix, not garden soil\n"
    "- [ ] Water until it runs from the base\n"
    "- [ ] Move the pot into six hours of sun\n"
)

WORKFLOW_BLOCK = (
    "1. Soak the root ball for ten minutes before planting.\n"
    "2. Half-fill the container with moist potting mix.\n"
    "3. Set the plant so its crown sits level with the rim.\n"
    "4. Top up, firm gently, then water in well.\n"
)


def _outline(n=9):
    """An outline whose purposes contain none of the old trigger keywords."""
    return [
        {
            "order": i,
            "title": f"Chapter {i}: Step {i} of growing in pots",
            "purpose": f"Teach readers the practical work of step {i} in plain language.",
        }
        for i in range(1, n + 1)
    ]


def _data(n=9):
    return {"product_type": "ebook", "outline": _outline(n)}


def _contract(n=9):
    return build_book_contract(_data(n))


# ============================== the contract now demands designable material ==


def test_a_generic_book_requires_checklists_and_workflows():
    """The live failure: nothing was demanded, so nothing was written."""
    book = _contract(9)
    checklists = [c for c in book.chapters if c.required_checklist]
    workflows = [c for c in book.chapters if c.required_workflow]

    assert len(checklists) >= 3, "an interior needs real checklists to draw"
    assert len(workflows) >= 3, "an interior needs real numbered procedures to draw"


def test_the_requirements_do_not_land_on_the_same_chapters():
    """One chapter carrying everything leaves the rest bare."""
    book = _contract(9)
    both = [c for c in book.chapters if c.required_checklist and c.required_workflow]
    assert not both, f"chapters overloaded: {[c.order for c in both]}"


def test_some_chapters_are_left_free_for_a_photograph():
    """All-text-box interiors are the defect the editorial floor rejects."""
    book = _contract(9)
    bare = [c for c in book.chapters
            if not c.required_checklist and not c.required_workflow]
    assert len(bare) >= 3, "the interior still needs photographs"


def test_the_assignment_is_deterministic():
    """The outline digest must not wobble between two identical builds."""
    first = _contract(9)
    second = _contract(9)
    assert [(c.order, c.required_checklist, c.required_workflow) for c in first.chapters] == \
           [(c.order, c.required_checklist, c.required_workflow) for c in second.chapters]


@pytest.mark.parametrize("n", [6, 8, 9, 12])
def test_books_of_other_lengths_are_also_covered(n):
    book = _contract(n)
    assert any(c.required_checklist for c in book.chapters)
    assert any(c.required_workflow for c in book.chapters)


@pytest.mark.parametrize("n", [4, 5])
def test_a_very_short_book_still_gets_what_it_can_carry(n):
    """Four and five chapter books cannot satisfy the interior floor at all.

    It wants three photographs AND three distinct kinds, while capping any one
    kind at 55% of the set — three photographs out of four or five visuals is
    75% and 60%. One aid per chapter cannot meet both. That tension predates
    this change and is not hidden by it: the contract still asks for the
    structure the book CAN carry rather than silently asking for nothing.
    """
    book = _contract(n)
    assert any(c.required_checklist or c.required_workflow for c in book.chapters)


def test_a_very_short_book_is_not_overloaded():
    """Three chapters cannot carry three of everything and still breathe."""
    book = _contract(3)
    for c in book.chapters:
        assert not (c.required_checklist and c.required_workflow)


def test_the_writer_is_told_the_exact_accepted_format():
    """"Include a checklist" is not actionable; the shape must be named."""
    book = _contract(9)
    checklist_chapter = next(c for c in book.chapters if c.required_checklist)
    workflow_chapter = next(c for c in book.chapters if c.required_workflow)

    criteria = " ".join(checklist_chapter.acceptance_criteria).lower()
    assert "- [ ]" in criteria, "the checkbox shape must be spelled out"

    criteria = " ".join(workflow_chapter.acceptance_criteria).lower()
    assert "1." in criteria and "numbered" in criteria


# ===================== what is demanded is what the validator will accept ====


def test_the_demanded_checklist_satisfies_the_validator():
    body = "Some prose about pots.\n\n" + CHECKLIST_BLOCK
    assert _has_checklist(GENERIC_CHECKLIST_SPEC, [CHECKLIST_BLOCK], body) is True


def test_the_demanded_workflow_satisfies_the_validator():
    body = "Some prose about planting.\n\n" + WORKFLOW_BLOCK
    assert _has_workflow(GENERIC_WORKFLOW_SPEC, [WORKFLOW_BLOCK], body) is True


# ===================== what is demanded is what the interior can draw =======


def test_the_demanded_checklist_becomes_a_checklist_visual():
    body = "Prose about drainage.\n\n" + CHECKLIST_BLOCK
    assert len(_parse_checkbox_items(body)) >= 4
    aid = _choose_aid(2, "Chapter 2: Step 2 of growing in pots", body)
    assert aid is not None and aid["type"] == "checklist"


def test_the_demanded_workflow_becomes_a_workflow_visual():
    body = "Prose about planting day.\n\n" + WORKFLOW_BLOCK
    assert len(_parse_workflow(body)) >= 3
    aid = _choose_aid(3, "Chapter 3: Step 3 of growing in pots", body)
    assert aid is not None and aid["type"] == "workflow"


def test_a_printed_table_does_not_hide_the_checklist_visual():
    """The interior typesets tables itself, so a table chapter must still
    yield a drawable visual rather than falling through to nothing."""
    table = ("| Pot | Holds water |\n| --- | --- |\n"
             "| Plastic | Well |\n| Terracotta | Dries fast |\n")
    body = "Prose.\n\n" + table + "\n" + CHECKLIST_BLOCK
    aid = _choose_aid(2, "Chapter 2: Step 2 of growing in pots", body)
    assert aid is not None and aid["type"] == "checklist"


# ======================= a book built to contract clears the interior floor ==


def _asked_count(criteria) -> int:
    """The exact number of items/steps the contract asked this chapter for."""
    import re

    for line in criteria:
        m = re.search(r"exactly (\d+) (?:items|steps)", str(line))
        if m:
            return int(m.group(1))
    raise AssertionError(f"no explicit count in criteria: {criteria}")


def _plan_from_contract(n=9):
    """Build the interior plan a book written to this contract would yield.

    Each chapter's structured block is written with its own content, as a real
    chapter's would be: three chapters repeating one identical checklist is a
    monotonous interior, and the editorial floor is right to say so.
    """
    book = _contract(n)
    chapters = []
    for c in book.chapters:
        body = f"Practical prose for {c.title}, written for a beginner.\n\n"
        if c.required_checklist:
            body += f"**{c.title} checklist**\n\n" + "".join(
                f"- [ ] Task {i} to finish step {c.order} properly\n"
                for i in range(1, _asked_count(c.acceptance_criteria) + 1)
            )
        if c.required_workflow:
            body += "".join(
                f"{i}. Action {i} while working through step {c.order}.\n"
                for i in range(1, _asked_count(c.acceptance_criteria) + 1)
            )
        aid = _choose_aid(c.order, c.title, body)
        if aid is None:
            # No structured material: the interior uses a photograph here.
            aid = {"type": "photo", "required": True, "chapter": c.title}
        chapters.append({"chapter": c.title, "aids": [aid]})
    return {"title": "Container Gardening for Beginners", "chapters": chapters}


#: Findings that are this change's responsibility. The rest of what
#: review_visual_set checks -- attribution, captions, rendered pixel size --
#: belongs to photo acquisition and rendering, which this test does not run.
_MONOTONY = (
    "kind(s) of visual across",
    "are the same kind",
    "box of text lines",
    "photograph(s) for a subject that supports them",
    "repeats the design of",
    "no interior visuals",
)


def test_a_manuscript_written_to_this_contract_clears_the_variety_floor():
    """The end-to-end point of the change, with no model and no network."""
    verdict = review_visual_set(
        _plan_from_contract(9), chapter_count=9, photography_supported=True)

    assert verdict.photograph_count >= 3
    assert verdict.illustrative_count >= 3
    assert len(verdict.type_counts) >= 3, verdict.type_counts

    monotony = [f for f in verdict.findings if any(m in f for m in _MONOTONY)]
    assert not monotony, f"interior still reads as a template: {monotony}"


def test_the_exact_live_refusal_no_longer_happens():
    """"Only 1 kind(s) of visual across 9: photo." killed a finished book."""
    verdict = review_visual_set(
        _plan_from_contract(9), chapter_count=9, photography_supported=True)
    assert not any("Only 1 kind" in f for f in verdict.findings)


@pytest.mark.parametrize("n", [6, 8, 9, 12])
def test_other_book_lengths_also_clear_the_variety_floor(n):
    verdict = review_visual_set(
        _plan_from_contract(n), chapter_count=n, photography_supported=True)
    monotony = [f for f in verdict.findings if any(m in f for m in _MONOTONY)]
    assert not monotony, f"{n} chapters: {monotony}"


# ========================================= the acceptance catalog is intact ==


def test_the_event_photography_catalog_is_not_touched():
    """Its chapters carry hand-written specs that must not be overwritten."""
    from services.ebook_manuscript_engine import event_photo_catalog_by_title

    catalog = event_photo_catalog_by_title()
    assert catalog, "the catalog should still exist"
    specs = list(catalog.values())
    assert any(s.required_table for s in specs)
    # Its specs are named, not the generic placeholders.
    assert not any(s.required_checklist == GENERIC_CHECKLIST_SPEC for s in specs)


# ================== a requirement must be repairable, not just detectable ===


class TestTheRepairPromptNamesTheFormat:
    """A finding the generator cannot act on is not a requirement, it is a trap.

    Chapter 6 of "Container Gardening" was repaired six times and every repair
    wrote more prose, because the instruction it was handed read "Missing
    required workflow: chapter-workflow" -- an internal spec name. The table
    branch had already learned this lesson ("'Fix the chapter' is not
    actionable when the failure is a format the model may believe it already
    satisfied in prose"); workflow and checklist had never been given one.
    """

    @staticmethod
    def _instruction(finding):
        from services.ebook_manuscript_engine import format_unresolved_findings_for_prompt

        out = format_unresolved_findings_for_prompt([finding])
        assert out, f"no instruction produced for {finding!r}"
        return " ".join(out)

    def test_the_workflow_repair_spells_out_the_numbered_list(self):
        text = self._instruction(
            "MISSING_REQUIRED_WORKFLOW: Missing required workflow: chapter-workflow")
        assert "1." in text and "2." in text
        assert "numbered" in text.lower()
        assert "prose" in text.lower(), "it must say prose does not count"

    def test_the_checklist_repair_spells_out_the_checkbox(self):
        text = self._instruction(
            "MISSING_REQUIRED_CHECKLIST: Missing required checklist: chapter-checklist")
        assert "[ ]" in text, "the checkbox shape must appear literally"
        assert "four" in text.lower()

    def test_neither_repair_leaks_the_internal_spec_name_as_content(self):
        for finding in (
            "MISSING_REQUIRED_WORKFLOW: Missing required workflow: chapter-workflow",
            "MISSING_REQUIRED_CHECKLIST: Missing required checklist: chapter-checklist",
        ):
            text = self._instruction(finding)
            assert "chapter-workflow" not in text
            assert "chapter-checklist" not in text
            assert "do not quote this finding" in text.lower()

    def test_a_repaired_chapter_then_satisfies_the_validator(self):
        """What the instruction asks for is what the validator accepts."""
        from services.ebook_manuscript_engine import _has_checklist, _has_workflow

        assert _has_workflow(GENERIC_WORKFLOW_SPEC, [], WORKFLOW_BLOCK) is True
        assert _has_checklist(GENERIC_CHECKLIST_SPEC, [], CHECKLIST_BLOCK) is True


# ================ an internal spec name must never reach the printed book ===


class TestLeakedSpecNamesAreStripped:
    """The model printed "### chapter-workflow" above the list it had written.

    Preflight caught it as a production heading -- but only after the
    manuscript was approved, so the book had no way forward: the stage was
    COMPLETE and nothing would repair it. The sanitizer already strips finding
    echoes like "MISSING_REQUIRED_WORKFLOW:"; a bare spec name used as a
    heading slipped straight through it.
    """

    @staticmethod
    def _clean(md):
        from services.ebook_document import sanitize_leaked_production_labels

        return sanitize_leaked_production_labels(md)

    @pytest.mark.parametrize(
        "heading",
        ["### chapter-workflow", "## chapter-checklist", "**chapter-comparison**",
         "chapter-workflow", "#### Chapter-Workflow"],
    )
    def test_a_leaked_spec_heading_is_removed(self, heading):
        md = f"Real prose about pots.\n\n{heading}\n\n1. Do the thing.\n"
        cleaned, removed = self._clean(md)
        assert "chapter-workflow" not in cleaned.lower()
        assert "chapter-checklist" not in cleaned.lower()
        assert "chapter-comparison" not in cleaned.lower()
        assert removed, "the removal should be reported"

    def test_the_readers_content_is_kept(self):
        md = ("Real prose about pots.\n\n### chapter-workflow\n\n"
              "1. Check soil moisture with a finger.\n"
              "2. Water until it runs from the base.\n"
              "3. Move the pot back into the sun.\n")
        cleaned, _ = self._clean(md)
        assert "Check soil moisture with a finger." in cleaned
        assert "Water until it runs from the base." in cleaned
        assert "Real prose about pots." in cleaned

    def test_ordinary_prose_mentioning_a_chapter_is_untouched(self):
        md = "This chapter - workflow and all - takes about an hour.\n"
        cleaned, _ = self._clean(md)
        assert "takes about an hour" in cleaned


def test_the_exact_preflight_failure_is_prevented():
    """production_heading 'chapter-workflow' blocked a finished book."""
    from services.ebook_document import sanitize_leaked_production_labels

    body = (
        "They can maintain a productive garden without excessive time.\n\n"
        "### chapter-workflow\n\n"
        "1. Check soil moisture by inserting a finger into the soil.\n"
        "2. Water deeply until it drains from the base.\n"
        "3. Empty the saucer so roots never sit in water.\n"
    )
    cleaned, removed = sanitize_leaked_production_labels(body)
    assert "chapter-workflow" not in cleaned
    assert len(_parse_workflow(cleaned)) >= 3, "the workflow itself must survive"
