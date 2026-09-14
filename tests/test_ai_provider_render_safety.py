"""The live manuscript stage kept failing after Resume Build was fixed.

ROOT CAUSE THIS GUARDS
-----------------------
A real production build of "Container Gardening for Beginners" reached the
manuscript stage and failed every time with:

    urllib.error.URLError: <urlopen error [Errno 111] Connection refused>

via services/ebook.py::generate_one_chapter -> routes_local -> chat_with_meta
-> LocalAIProvider -> http://127.0.0.1:11434 (the owner's local Ollama, which
does not exist on Render).

services/ai_providers.py's Local Manuscript Pilot (added 2026-09-03, ec9d3ee)
routes chapter generation to a local engine by default (POLICY_LOCAL_FIRST)
unless FACTORY_AI_POLICY is explicitly set to "premium". The owner set
FACTORY_AI_POLICY=premium on Render and redeployed; the failure persisted.

tests/test_ai_providers.py already proves routes_local()/select_provider()
correctly respect FACTORY_AI_POLICY=premium when it IS read -- that logic is
not the bug. The real gap is architectural: nothing in the hosted runtime
ever REQUIRED that one custom variable to be set correctly. A stray .env file
(app.py's load_dotenv runs with override=True outside test mode -- see its
own comment describing an identical failure shape for TAVILY_API_KEY on
2026-08-29), a typo, a stale process that never picked up the new value, or a
future redeploy that simply forgets to carry the setting forward would all
silently reproduce the exact same customer-facing dead end.

THE FIX
-------
routes_local() now also checks _running_on_render(): Render sets RENDER=true
automatically on every deployed service, a signal the owner cannot forget to
set and that cannot be shadowed by a hand-edited .env file. When that signal
is present, local routing is refused unconditionally -- independent of
FACTORY_AI_POLICY. Local development (RENDER unset) is completely unaffected:
FACTORY_AI_POLICY continues to govern exactly as before.

No external/paid call is made by any test here.
"""
from __future__ import annotations

import json
import urllib.error
from unittest.mock import patch

import pytest

from services import ai_providers
from services.ai_providers import (
    LocalAIProvider,
    OpenAIProvider,
    routes_local,
    select_provider,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Every test starts from a known, local-development-shaped environment."""
    monkeypatch.delenv("FACTORY_AI_POLICY", raising=False)
    monkeypatch.delenv("FACTORY_TEST_MODE", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.setenv("FACTORY_LOCAL_AI_MODEL", "qwen2.5:7b-instruct")
    monkeypatch.setenv("FACTORY_LOCAL_AI_URL", "http://127.0.0.1:11434")
    ai_providers.reset_providers()
    yield
    ai_providers.reset_providers()


def _urlopen_that_refuses(*_a, **_kw):
    raise urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))


# -------------------------------------------------------- the hosted floor ---


def test_render_blocks_local_routing_even_with_the_default_policy(monkeypatch):
    """Reproduces the exact live bug: RENDER set, no explicit policy at all."""
    monkeypatch.setenv("RENDER", "true")
    assert ai_providers.get_policy() == ai_providers.POLICY_LOCAL_FIRST, (
        "the default policy is still local-first -- Render must override it structurally"
    )
    assert routes_local("chapter") is False
    assert isinstance(select_provider("chapter"), OpenAIProvider)


def test_render_blocks_local_routing_even_if_policy_is_explicitly_local(monkeypatch):
    """A misconfigured/mistaken policy on Render must not be able to reach it."""
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("FACTORY_AI_POLICY", "local_only")
    assert routes_local("chapter") is False
    assert routes_local("chapter_repair") is False
    assert isinstance(select_provider("chapter"), OpenAIProvider)


def test_render_blocks_local_routing_with_premium_policy_too(monkeypatch):
    """premium already worked in isolation; this proves the belt-and-braces floor agrees."""
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("FACTORY_AI_POLICY", "premium")
    assert routes_local("chapter") is False
    assert isinstance(select_provider("chapter"), OpenAIProvider)


def test_the_hosted_path_never_opens_a_socket_to_127_0_0_1(monkeypatch):
    """The actual customer-facing proof: no network call is even attempted."""
    monkeypatch.setenv("RENDER", "true")

    class _Msg:
        content = "text"

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]

    class _Client:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                def create(**_kwargs):
                    return _Resp()

    with patch("ai_client.get_client", return_value=_Client()), \
         patch("urllib.request.urlopen", side_effect=_urlopen_that_refuses) as mocked:
        result = ai_providers.generate("sys", "user", 512, task="chapter")
    mocked.assert_not_called()
    assert result.provider == "openai"


def test_render_variable_being_blank_does_not_count_as_hosted(monkeypatch):
    """RENDER="" (unset-but-present in some shells) must not falsely trip the floor."""
    monkeypatch.setenv("RENDER", "")
    assert ai_providers._running_on_render() is False
    assert routes_local("chapter") is True, "local development must be unaffected"


# --------------------------------------------------- local dev is unaffected ---


def test_local_development_still_routes_local_by_default(monkeypatch):
    """RENDER unset (every local dev machine): existing behaviour is unchanged."""
    assert ai_providers._running_on_render() is False
    assert routes_local("chapter") is True
    assert isinstance(select_provider("chapter"), LocalAIProvider)


def test_local_development_still_honors_an_explicit_premium_choice(monkeypatch):
    monkeypatch.setenv("FACTORY_AI_POLICY", "premium")
    assert routes_local("chapter") is False
    assert isinstance(select_provider("chapter"), OpenAIProvider)


def test_unrelated_tasks_are_unaffected_by_the_render_floor(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    assert routes_local("research") is False
    assert routes_local(None) is False


# --------------------------------------------------- the real call chain ---


from dataclasses import dataclass, field


class _FakeBook:
    pass


@dataclass
class _FakeChapter:
    order: int = 1
    title: str = "Test Chapter"
    unresolved_findings: list = field(default_factory=list)


def test_generate_one_chapter_uses_openai_on_render_never_touching_local(monkeypatch):
    """Exercises the exact production function named in the live traceback."""
    monkeypatch.setenv("RENDER", "true")

    monkeypatch.setattr(
        "services.ebook_manuscript_engine.assigned_research_for_chapter",
        lambda book, chapter: "research",
    )
    monkeypatch.setattr(
        "services.ebook_manuscript_engine.chapter_contract_prompt",
        lambda book, chapter: "prompt",
    )
    monkeypatch.setattr(
        "services.ebook_manuscript_engine.format_unresolved_findings_for_prompt",
        lambda findings: findings,
    )

    class _Msg:
        content = "Chapter text."

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]

    class _Client:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                def create(**_kwargs):
                    return _Resp()

    with patch("ai_client.get_client", return_value=_Client()), \
         patch("urllib.request.urlopen", side_effect=_urlopen_that_refuses) as mocked:
        from services.ebook import generate_one_chapter

        out = generate_one_chapter(_FakeBook(), _FakeChapter())

    mocked.assert_not_called()
    assert out["provider"] == "openai"
    assert out["chapter"] == "Chapter text."
    assert out["billable_calls"] == 1


# ------------------------------------------- resume after a real provider ---
# failure, through the real chapter engine (not the fixture generate_fn used
# by tests/test_local_manuscript_pilot.py). This is the exact shape of the
# live incident: one or more chapters already accepted, the next one fails at
# the provider boundary, and Resume Build must continue without re-billing or
# regenerating what already passed.


def test_resume_after_a_real_provider_failure_never_regenerates_accepted_chapters(monkeypatch):
    from dataclasses import asdict

    from services.ebook_manuscript_engine import BookContract, ChapterContract, run_chapter_pipeline

    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(
        "services.ebook_manuscript_engine.assigned_research_for_chapter",
        lambda book, chapter: "research",
    )
    monkeypatch.setattr(
        "services.ebook_manuscript_engine.chapter_contract_prompt",
        lambda book, chapter: "prompt",
    )
    monkeypatch.setattr(
        "services.ebook_manuscript_engine.format_unresolved_findings_for_prompt",
        lambda findings: findings,
    )

    book = BookContract(
        title="Container Gardening for Beginners", subtitle="", author="Author",
        audience="beginners", primary_outcome="a finished container garden",
        approved_outline=[], research_brief="brief", citations=[], editorial_rules=[],
        target_word_min=0, target_word_max=100000,
        chapters=[
            ChapterContract(order=1, title="Chapter 1", purpose="p", min_useful_words=1),
            ChapterContract(order=2, title="Chapter 2", purpose="p", min_useful_words=1),
        ],
    )

    class _Msg:
        content = "Chapter body text, long enough to stand in for real prose."

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]

    calls: list[str] = []
    chapter_two_attempts = {"n": 0}

    def _client_that_fails_on_chapter_two(**kwargs):
        content = kwargs["messages"][1]["content"]
        calls.append(content)
        if "Chapter 2" in content:
            chapter_two_attempts["n"] += 1
            if chapter_two_attempts["n"] == 1:
                # The original live failure: the provider was unreachable.
                raise ai_providers.ProviderUnavailable("simulated provider outage")
        return _Resp()

    class _Client:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                def create(**kwargs):
                    return _client_that_fails_on_chapter_two(**kwargs)

    from services.ebook import generate_one_chapter

    saved: dict[str, list] = {"chapters": []}

    def _capture(accepted):
        saved["chapters"] = list(accepted)

    with patch("ai_client.get_client", return_value=_Client()):
        with pytest.raises(ai_providers.ProviderUnavailable):
            run_chapter_pipeline(
                book, generate_chapter_fn=generate_one_chapter, on_chapter_accepted=_capture,
            )

    assert len(saved["chapters"]) == 1, "only chapter 1 should have been accepted before the failure"
    resumed_from = list(saved["chapters"])
    calls.clear()

    # --- Resume Build: the same call, with what was already accepted ---
    with patch("ai_client.get_client", return_value=_Client()):
        pipeline = run_chapter_pipeline(
            book, generate_chapter_fn=generate_one_chapter, accepted_chapters=resumed_from,
        )

    assert len(calls) == 1, "resume must generate only the one remaining chapter, not chapter 1 again"
    assert "Chapter 2" in calls[0]
    assert len(pipeline["accepted_chapters"]) == 2
