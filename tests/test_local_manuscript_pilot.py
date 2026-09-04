"""Local Manuscript Pilot: persistence, resume, accounting, bounded repair.

All chapter generation here is mocked. No provider is contacted, no paid call
is made, and no ebook is exported.
"""
from __future__ import annotations

import pytest

from services.ebook_manuscript_engine import (
    MAX_LOCAL_REPAIR_ATTEMPTS,
    BookContract,
    ChapterContract,
    run_chapter_pipeline,
)


# --------------------------------------------------------------- helpers ---


#: The chapter validator checks that the body actually covers the contract
#: purpose, so the fixture purpose and fixture body must share vocabulary.
#: Every 5+ letter token here appears in _chapter_body below.
_PURPOSE = "Keep meals inside an insulated container and verify temperature"


def _chapter_body(title: str, repeats: int = 40) -> str:
    """A body that genuinely satisfies validate_chapter.

    Deliberately free of numerals and marketing language: the validator rejects
    unsupported numeric/outcome claims, and this fixture is about persistence
    and routing, not about exercising those rules.
    """
    sentence = (
        "Pack the insulated container with a chilled gel pack before the shift "
        "begins, then verify the internal temperature using a probe thermometer. "
    )
    return (
        f"## {title}\n\n"
        f"{sentence * repeats}\n\n"
        "- Chill the insulated container overnight.\n"
        "- Add the chilled gel pack.\n"
        "- Verify the temperature midway through the shift.\n"
    )


def _book(n_chapters: int = 4) -> BookContract:
    chapters = [
        ChapterContract(
            order=i,
            title=f"Chapter {i}",
            purpose=_PURPOSE,
            min_useful_words=50,
        )
        for i in range(1, n_chapters + 1)
    ]
    return BookContract(
        title="Test Book",
        subtitle="Subtitle",
        author="Author",
        audience="testers",
        primary_outcome="an outcome",
        approved_outline=[{"title": c.title, "purpose": c.purpose} for c in chapters],
        research_brief="A short research brief for testing.",
        citations=[],
        editorial_rules=[],
        target_word_min=0,
        target_word_max=100000,
        chapters=chapters,
    )


def _local_gen(fail_orders=None, record=None):
    """A generate_chapter_fn that reports itself as the local provider."""
    fail_orders = set(fail_orders or [])

    def _gen(book, chapter):
        if record is not None:
            record.append(chapter.order)
        body = "too short" if chapter.order in fail_orders else _chapter_body(chapter.title)
        return {
            "chapter": body,
            "ebook": body,
            "assigned_research": "",
            "chapter_contract": {},
            "billable_calls": 0,
            "provider": "local",
        }

    return _gen


def _openai_gen(record=None):
    """Legacy-shaped provider that does NOT report billable_calls."""

    def _gen(book, chapter):
        if record is not None:
            record.append(chapter.order)
        body = _chapter_body(chapter.title)
        return {"chapter": body, "ebook": body, "assigned_research": "", "chapter_contract": {}}

    return _gen


# ------------------------------------------------------- zero-billable ---


def test_local_chapters_are_zero_billable():
    pipeline = run_chapter_pipeline(_book(3), generate_chapter_fn=_local_gen())
    assert pipeline["chapter_calls"] == 3
    assert pipeline["billable_chapter_calls"] == 0
    assert pipeline["providers_used"] == ["local"]


def test_legacy_provider_accounting_is_unchanged():
    """A caller that reports no billable_calls must still be charged per call."""
    pipeline = run_chapter_pipeline(_book(3), generate_chapter_fn=_openai_gen())
    assert pipeline["chapter_calls"] == 3
    assert pipeline["billable_chapter_calls"] == 3, "existing OpenAI accounting must not change"


# ---------------------------------------------------- incremental saving ---


def test_each_accepted_chapter_persists_immediately():
    saves: list[int] = []

    def _on_accepted(accepted):
        saves.append(len(accepted))

    run_chapter_pipeline(
        _book(4), generate_chapter_fn=_local_gen(), on_chapter_accepted=_on_accepted
    )
    assert saves == [1, 2, 3, 4], "a save must happen after every accepted chapter"


def test_interruption_preserves_completed_chapters():
    """Chapter 3 explodes. Chapters 1-2 must already be saved."""
    saved_state: dict[str, list] = {"chapters": []}

    def _on_accepted(accepted):
        saved_state["chapters"] = [{"order": c.order, "title": c.title, "body": c.body}
                                   for c in accepted]

    def _gen(book, chapter):
        if chapter.order == 3:
            raise RuntimeError("simulated interruption: provider died mid-book")
        body = _chapter_body(chapter.title)
        return {"chapter": body, "ebook": body, "assigned_research": "",
                "chapter_contract": {}, "billable_calls": 0, "provider": "local"}

    with pytest.raises(RuntimeError, match="simulated interruption"):
        run_chapter_pipeline(_book(5), generate_chapter_fn=_gen,
                             on_chapter_accepted=_on_accepted)

    orders = [c["order"] for c in saved_state["chapters"]]
    assert orders == [1, 2], "chapters 1-2 must survive the interruption"


def test_a_failing_save_does_not_lose_the_chapter():
    """Persistence is best effort: a bad save must not discard passing work."""

    def _bad_save(_accepted):
        raise OSError("disk full")

    pipeline = run_chapter_pipeline(
        _book(2), generate_chapter_fn=_local_gen(), on_chapter_accepted=_bad_save
    )
    assert len(pipeline["accepted_chapters"]) == 2


# ------------------------------------------------------------- resuming ---


def test_resume_does_not_regenerate_accepted_chapters():
    """The core resume guarantee."""
    first_calls: list[int] = []
    saved: dict[str, list] = {"chapters": []}

    def _capture(accepted):
        saved["chapters"] = list(accepted)

    def _gen_fail_at_3(book, chapter):
        first_calls.append(chapter.order)
        if chapter.order == 3:
            raise RuntimeError("interrupted")
        body = _chapter_body(chapter.title)
        return {"chapter": body, "ebook": body, "assigned_research": "",
                "chapter_contract": {}, "billable_calls": 0, "provider": "local"}

    with pytest.raises(RuntimeError):
        run_chapter_pipeline(_book(5), generate_chapter_fn=_gen_fail_at_3,
                             on_chapter_accepted=_capture)

    assert first_calls == [1, 2, 3]
    resumed_from = list(saved["chapters"])
    assert [c.order for c in resumed_from] == [1, 2]

    # --- resume ---
    second_calls: list[int] = []
    pipeline = run_chapter_pipeline(
        _book(5),
        generate_chapter_fn=_local_gen(record=second_calls),
        accepted_chapters=resumed_from,
    )

    assert 1 not in second_calls, "chapter 1 must NOT be regenerated"
    assert 2 not in second_calls, "chapter 2 must NOT be regenerated"
    assert second_calls == [3, 4, 5], "resume must start at the first unfinished chapter"
    assert len(pipeline["accepted_chapters"]) == 5


# ------------------------------------------------------- bounded repair ---


def test_local_failure_is_repaired_within_bounds_then_marked():
    """Initial attempt + at most 2 repairs, then stop. Never a paid call."""
    attempts: list[int] = []

    def _always_fails(book, chapter):
        attempts.append(chapter.order)
        return {"chapter": "too short", "ebook": "too short", "assigned_research": "",
                "chapter_contract": {}, "billable_calls": 0, "provider": "local"}

    pipeline = run_chapter_pipeline(_book(2), generate_chapter_fn=_always_fails)

    # chapter 1: 1 initial + 2 repairs = 3 attempts, then stop_on_failure halts.
    assert attempts.count(1) == 1 + MAX_LOCAL_REPAIR_ATTEMPTS
    assert pipeline["billable_chapter_calls"] == 0, "repairs must stay free"
    rec = pipeline["provider_payloads"][0]
    assert rec["local_repair_attempts"] == MAX_LOCAL_REPAIR_ATTEMPTS
    assert rec["needs_premium_enhancement"] is True


def test_local_repair_can_succeed_on_second_attempt():
    state = {"n": 0}

    def _fails_once(book, chapter):
        state["n"] += 1
        body = "too short" if state["n"] == 1 else _chapter_body(chapter.title)
        return {"chapter": body, "ebook": body, "assigned_research": "",
                "chapter_contract": {}, "billable_calls": 0, "provider": "local"}

    pipeline = run_chapter_pipeline(_book(1), generate_chapter_fn=_fails_once)
    assert len(pipeline["accepted_chapters"]) == 1
    assert pipeline["provider_payloads"][0]["local_repair_attempts"] == 1
    assert pipeline["billable_chapter_calls"] == 0


def test_paid_provider_is_not_retried_by_the_local_repair_loop():
    """Repair is free-only. A paid provider keeps single-attempt behaviour."""
    attempts: list[int] = []

    def _paid_fails(book, chapter):
        attempts.append(chapter.order)
        return {"chapter": "too short", "ebook": "too short",
                "assigned_research": "", "chapter_contract": {}}

    run_chapter_pipeline(_book(2), generate_chapter_fn=_paid_fails)
    assert attempts.count(1) == 1, "a paid chapter must not be silently retried"


def test_failed_local_chapter_never_calls_a_paid_provider():
    """The cost guarantee: exhausted local repair does not escalate."""
    providers: list[str] = []

    def _always_fails(book, chapter):
        providers.append("local")
        return {"chapter": "no", "ebook": "no", "assigned_research": "",
                "chapter_contract": {}, "billable_calls": 0, "provider": "local"}

    pipeline = run_chapter_pipeline(_book(1), generate_chapter_fn=_always_fails)
    assert set(providers) == {"local"}
    assert pipeline["providers_used"] == ["local"]
    assert pipeline["billable_chapter_calls"] == 0


def test_budget_cap_does_not_limit_free_local_chapters():
    """max_chapter_calls is a spending bound, not a generation bound."""
    calls: list[int] = []
    pipeline = run_chapter_pipeline(
        _book(6), generate_chapter_fn=_local_gen(record=calls), max_chapter_calls=2
    )
    assert len(calls) == 6, "free chapters must not be capped by a dollar budget"
    assert pipeline["billable_chapter_calls"] == 0


def test_budget_cap_still_limits_paid_chapters():
    calls: list[int] = []
    run_chapter_pipeline(
        _book(6), generate_chapter_fn=_openai_gen(record=calls), max_chapter_calls=2
    )
    assert len(calls) == 2, "paid chapters must still respect the budget cap"
