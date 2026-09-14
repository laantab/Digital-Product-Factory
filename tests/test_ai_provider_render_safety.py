"""The live manuscript stage kept failing even after a first attempted fix.

ROOT CAUSE THIS GUARDS (the full story, in order)
--------------------------------------------------
A real production build of "Container Gardening for Beginners" reached the
manuscript stage and failed every time with:

    services.ai_providers.ProviderUnavailable: Local engine unreachable at
    http://127.0.0.1:11434/api/chat: [Errno 111] Connection refused

via services/ebook.py::generate_one_chapter -> ai_client.py::chat_with_meta
-> services/ai_providers.py::generate -> LocalAIProvider -> 127.0.0.1:11434
(the owner's local Ollama, which does not exist on the hosted Factory).

FIRST ATTEMPTED FIX (superseded -- kept here as documented history)
---------------------------------------------------------------------
services/ai_providers.py's Local Manuscript Pilot (added 2026-09-03,
ec9d3ee) routed chapter generation to a local engine by default
(POLICY_LOCAL_FIRST) unless FACTORY_AI_POLICY was explicitly "premium". The
owner set FACTORY_AI_POLICY=premium on the host and redeployed; the failure
persisted. A first fix added a check for a RENDER environment variable,
assumed (not verified) to be auto-injected by the hosting platform, and
hard-blocked local routing when present. THE OWNER RAN A NEW LIVE BUILD
AFTER THAT FIX DEPLOYED AND GOT THE IDENTICAL FAILURE -- proving the RENDER
signal was not reliably present in the actual deployed runtime. Guessing
about the environment, twice, was the mistake.

THE ACTUAL FIX
---------------
The default itself changed. DEFAULT_POLICY is now POLICY_PREMIUM (cloud),
not POLICY_LOCAL_FIRST. routes_local() no longer tries to detect which
platform it is running on at all -- there is nothing left to detect.
FACTORY_AI_POLICY must be explicitly set to "local_first" or "local_only",
on the process that will actually generate the chapter, for local routing
to ever happen. Missing, empty, misspelled, or not carried forward on a
redeploy all mean the same thing: the paid cloud provider. This is safe on
any hosting platform, present or future, without needing to recognize it.

Local development keeps working exactly as before -- it now requires one
explicit line in .env (FACTORY_AI_POLICY=local_first) that this repository's
own .env now carries, so nothing changed for the person actually running
Ollama on their own machine.

No external/paid call is made by any test here.
"""
from __future__ import annotations

import urllib.error
from dataclasses import dataclass, field
from unittest.mock import patch

import pytest

import ai_client  # noqa: F401 -- imported at collection time, not lazily inside a
# test, so its one-time module-level load_dotenv(override=True) (ai_client.py)
# fires once, now, before any test's monkeypatch.delenv runs. Deferring this
# import (e.g. relying on patch("ai_client.get_client", ...) to trigger it
# lazily) let that one-time dotenv load re-inject .env's FACTORY_AI_POLICY
# mid-test, silently undoing this file's own env cleanup -- the same class of
# hazard this whole file exists to guard production code against.
from services import ai_providers
from services.ai_providers import (
    LocalAIProvider,
    OpenAIProvider,
    routes_local,
    select_provider,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Every test starts from a HOSTED-shaped environment: nothing opted in.

    This is deliberately the opposite baseline from tests/test_ai_providers.py
    (which is specifically about the Local Manuscript Pilot's own mechanism
    and opts in by default). Here, the default is what an actual hosted
    deployment looks like on day one: no FACTORY_AI_POLICY set at all.
    """
    monkeypatch.delenv("FACTORY_AI_POLICY", raising=False)
    monkeypatch.delenv("FACTORY_TEST_MODE", raising=False)
    monkeypatch.setenv("FACTORY_LOCAL_AI_MODEL", "qwen2.5:7b-instruct")
    monkeypatch.setenv("FACTORY_LOCAL_AI_URL", "http://127.0.0.1:11434")
    ai_providers.reset_providers()
    yield
    ai_providers.reset_providers()


def _urlopen_that_refuses(*_a, **_kw):
    raise urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))


def _openai_client(content: str = "text", *, on_call=None):
    class _Msg:
        pass

    class _Choice:
        pass

    class _Resp:
        pass

    class _Client:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                def create(**kwargs):
                    if on_call is not None:
                        on_call(**kwargs)
                    msg = _Msg()
                    msg.content = content
                    choice = _Choice()
                    choice.message = msg
                    resp = _Resp()
                    resp.choices = [choice]
                    return resp

    return _Client()


# ------------------------------------------------ safe by default (hosted) ---


def test_missing_policy_never_routes_local():
    """The exact production shape: nothing set. Must never reach 127.0.0.1."""
    assert ai_providers.get_policy() == ai_providers.POLICY_PREMIUM
    assert routes_local("chapter") is False
    assert routes_local("chapter_repair") is False
    assert isinstance(select_provider("chapter"), OpenAIProvider)


def test_unknown_policy_value_also_stays_safe():
    """A typo'd or corrupted value must fail closed to cloud, not local."""
    import os

    os.environ["FACTORY_AI_POLICY"] = "loca1_first"  # a plausible typo
    try:
        assert ai_providers.get_policy() == ai_providers.POLICY_PREMIUM
        assert routes_local("chapter") is False
    finally:
        del os.environ["FACTORY_AI_POLICY"]


def test_explicit_premium_still_stays_on_openai(monkeypatch):
    monkeypatch.setenv("FACTORY_AI_POLICY", "premium")
    assert routes_local("chapter") is False
    assert isinstance(select_provider("chapter"), OpenAIProvider)


def test_no_socket_is_opened_toward_the_local_engine_by_default():
    """The actual customer-facing proof: no network call is even attempted."""
    with patch("ai_client.get_client", return_value=_openai_client()), \
         patch("urllib.request.urlopen", side_effect=_urlopen_that_refuses) as mocked:
        result = ai_providers.generate("sys", "user", 512, task="chapter")
    mocked.assert_not_called()
    assert result.provider == "openai"


def test_unrelated_tasks_are_unaffected():
    assert routes_local("research") is False
    assert routes_local(None) is False


# ----------------------------------------------- local is opt-in, and works ---


def test_local_first_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("FACTORY_AI_POLICY", "local_first")
    assert routes_local("chapter") is True
    assert isinstance(select_provider("chapter"), LocalAIProvider)


def test_local_only_also_opts_in(monkeypatch):
    monkeypatch.setenv("FACTORY_AI_POLICY", "local_only")
    assert routes_local("chapter_repair") is True
    assert isinstance(select_provider("chapter_repair"), LocalAIProvider)


def test_local_opt_in_genuinely_still_reaches_ollama(monkeypatch):
    """Windows/local Ollama support is not removed -- only made opt-in."""
    import json

    monkeypatch.setenv("FACTORY_AI_POLICY", "local_first")

    class _FakeResp:
        def __init__(self, payload):
            self._payload = payload

        def read(self):
            return self._payload

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    body = json.dumps({"message": {"role": "assistant", "content": "local chapter text"},
                       "done_reason": "stop"}).encode("utf-8")

    def _fake_urlopen(req, timeout=None):
        assert "127.0.0.1:11434" in req.full_url
        return _FakeResp(body)

    with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
        result = ai_providers.generate("sys", "user", 256, task="chapter")

    assert result.provider == "local"
    assert result.text == "local chapter text"
    assert result.billable_calls == 0


# ------------------------------------------------------- the real call chain ---


class _FakeBook:
    pass


@dataclass
class _FakeChapter:
    order: int = 1
    title: str = "Test Chapter"
    unresolved_findings: list = field(default_factory=list)


def _patch_manuscript_engine_helpers(monkeypatch):
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


def test_generate_one_chapter_uses_openai_by_default_never_touching_local(monkeypatch):
    """Exercises the exact production function named in the live traceback."""
    _patch_manuscript_engine_helpers(monkeypatch)

    with patch("ai_client.get_client", return_value=_openai_client("Chapter text.")), \
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
# live incident: one or more chapters already accepted, the next one fails,
# and Resume Build must continue without re-billing or regenerating what
# already passed -- true for the default (cloud) path just as it always was
# for the local path.


def test_resume_after_a_real_provider_failure_never_regenerates_accepted_chapters(monkeypatch):
    from services.ebook_manuscript_engine import BookContract, ChapterContract, run_chapter_pipeline

    _patch_manuscript_engine_helpers(monkeypatch)

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

    calls: list[str] = []
    chapter_two_attempts = {"n": 0}

    def _on_call(**kwargs):
        content = kwargs["messages"][1]["content"]
        calls.append(content)
        if "Chapter 2" in content:
            chapter_two_attempts["n"] += 1
            if chapter_two_attempts["n"] == 1:
                # A transient cloud-provider outage -- nothing to do with Ollama.
                raise RuntimeError("simulated cloud provider outage")

    client = _openai_client("Chapter body text, long enough to stand in for real prose.",
                             on_call=_on_call)

    from services.ebook import generate_one_chapter

    saved: dict[str, list] = {"chapters": []}

    def _capture(accepted):
        saved["chapters"] = list(accepted)

    with patch("ai_client.get_client", return_value=client):
        with pytest.raises(RuntimeError):
            run_chapter_pipeline(
                book, generate_chapter_fn=generate_one_chapter, on_chapter_accepted=_capture,
            )

    assert len(saved["chapters"]) == 1, "only chapter 1 should have been accepted before the failure"
    resumed_from = list(saved["chapters"])
    calls.clear()

    # --- Resume Build: the same call, with what was already accepted ---
    with patch("ai_client.get_client", return_value=client):
        pipeline = run_chapter_pipeline(
            book, generate_chapter_fn=generate_one_chapter, accepted_chapters=resumed_from,
        )

    assert len(calls) == 1, "resume must generate only the one remaining chapter, not chapter 1 again"
    assert "Chapter 2" in calls[0]
    assert len(pipeline["accepted_chapters"]) == 2
