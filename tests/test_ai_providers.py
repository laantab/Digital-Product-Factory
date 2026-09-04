"""Provider boundary tests for the Local Manuscript Pilot.

No network. No paid calls. The local engine is mocked at the HTTP layer, and
the OpenAI path is asserted by observing whether it is reached at all -- never
by calling it.
"""
from __future__ import annotations

import json
import urllib.error
from unittest.mock import patch

import pytest

import ai_client
from services import ai_providers
from services.ai_providers import (
    LocalAIProvider,
    MalformedResponse,
    ModelMissing,
    OpenAIProvider,
    ProviderTimeout,
    ProviderUnavailable,
    routes_local,
    select_provider,
)


@pytest.fixture(autouse=True)
def _clean_providers(monkeypatch):
    """Each test gets fresh providers and an explicit policy.

    FACTORY_TEST_MODE is cleared here because these tests exercise the routing
    decision itself, which is disabled in test mode by design. Every network
    call below is still mocked -- nothing contacts a real engine.
    """
    monkeypatch.delenv("FACTORY_AI_POLICY", raising=False)
    monkeypatch.delenv("FACTORY_TEST_MODE", raising=False)
    monkeypatch.setenv("FACTORY_LOCAL_AI_MODEL", "qwen2.5:7b-instruct")
    monkeypatch.setenv("FACTORY_LOCAL_AI_URL", "http://127.0.0.1:11434")
    ai_providers.reset_providers()
    yield
    ai_providers.reset_providers()


def test_test_mode_disables_local_routing(monkeypatch):
    """A local engine is still a provider. Tests must never reach one.

    Regression: chapter_repair routed local under FACTORY_TEST_MODE and reached
    the real Ollama running on the machine, performing a genuine generation
    inside an automated test.
    """
    monkeypatch.setenv("FACTORY_TEST_MODE", "1")
    assert routes_local("chapter") is False
    assert routes_local("chapter_repair") is False
    assert isinstance(select_provider("chapter"), OpenAIProvider)


def _ollama_chat_body(content: str) -> bytes:
    return json.dumps({"message": {"role": "assistant", "content": content},
                       "done_reason": "stop"}).encode("utf-8")


class _FakeHTTPResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# ---------------------------------------------------------------- routing ---


def test_no_task_does_not_route_local():
    """Every pre-existing call site passes no task and must stay on OpenAI."""
    assert routes_local(None) is False
    assert isinstance(select_provider(None), OpenAIProvider)


def test_chapter_task_routes_local():
    assert routes_local("chapter") is True
    assert isinstance(select_provider("chapter"), LocalAIProvider)


def test_chapter_repair_task_routes_local():
    assert routes_local("chapter_repair") is True
    assert isinstance(select_provider("chapter_repair"), LocalAIProvider)


@pytest.mark.parametrize("task", ["research", "title", "outline", "visual_plan", "cover", ""])
def test_unrelated_tasks_stay_on_openai(task):
    """The pilot must not quietly capture any other Factory AI task."""
    assert routes_local(task) is False
    assert isinstance(select_provider(task), OpenAIProvider)


def test_premium_policy_forces_openai_even_for_chapters(monkeypatch):
    monkeypatch.setenv("FACTORY_AI_POLICY", "premium")
    ai_providers.reset_providers()
    assert routes_local("chapter") is False
    assert isinstance(select_provider("chapter"), OpenAIProvider)


def test_unknown_policy_falls_back_to_local_first(monkeypatch):
    monkeypatch.setenv("FACTORY_AI_POLICY", "nonsense-value")
    assert ai_providers.get_policy() == ai_providers.POLICY_LOCAL_FIRST


# ------------------------------------------------------- local generation ---


def test_local_generation_succeeds_and_is_not_billable():
    provider = LocalAIProvider()
    with patch("urllib.request.urlopen", return_value=_FakeHTTPResponse(
            _ollama_chat_body("Chapter one body text."))):
        result = provider.generate_text("sys", "user", 512)

    assert result.text == "Chapter one body text."
    assert result.provider == "local"
    assert result.billable_calls == 0, "a local chapter must never be charged"


def test_openai_result_reports_one_billable_call():
    """The paid path still counts as one billable call. Accounting unchanged."""
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

    with patch("ai_client.get_client", return_value=_Client()):
        result = OpenAIProvider().generate_text("sys", "user", 128)

    assert result.billable_calls == 1
    assert result.provider == "openai"


# ------------------------------------------------------------ failure modes ---


def test_local_provider_unavailable_raises():
    provider = LocalAIProvider()
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
        with pytest.raises(ProviderUnavailable):
            provider.generate_text("sys", "user", 64)


def test_local_timeout_raises_timeout():
    provider = LocalAIProvider()
    with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
        with pytest.raises(ProviderTimeout):
            provider.generate_text("sys", "user", 64)


def test_malformed_local_response_raises():
    provider = LocalAIProvider()
    with patch("urllib.request.urlopen", return_value=_FakeHTTPResponse(b"<html>not json</html>")):
        with pytest.raises(MalformedResponse):
            provider.generate_text("sys", "user", 64)


def test_local_response_missing_content_raises():
    body = json.dumps({"message": {"role": "assistant"}}).encode("utf-8")
    provider = LocalAIProvider()
    with patch("urllib.request.urlopen", return_value=_FakeHTTPResponse(body)):
        with pytest.raises(MalformedResponse):
            provider.generate_text("sys", "user", 64)


def test_empty_local_response_raises():
    provider = LocalAIProvider()
    with patch("urllib.request.urlopen", return_value=_FakeHTTPResponse(_ollama_chat_body("   "))):
        with pytest.raises(MalformedResponse):
            provider.generate_text("sys", "user", 64)


def test_model_missing_is_reported_distinctly():
    body = json.dumps({"error": "model 'qwen2.5:7b-instruct' not found, try pulling it"}).encode()
    provider = LocalAIProvider()
    with patch("urllib.request.urlopen", return_value=_FakeHTTPResponse(body)):
        with pytest.raises(ModelMissing):
            provider.generate_text("sys", "user", 64)


# ------------------------------------------------------------ health check ---


def test_health_check_reports_unreachable():
    provider = LocalAIProvider()
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
        health = provider.health_check()
    assert health["ok"] is False
    assert health["reachable"] is False
    assert "Try Again" in health["customer_message"]


def test_health_check_reports_model_missing_when_none_pulled():
    """The exact state of this machine today: engine up, zero models."""
    body = json.dumps({"models": []}).encode("utf-8")
    provider = LocalAIProvider()
    with patch("urllib.request.urlopen", return_value=_FakeHTTPResponse(body)):
        health = provider.health_check()
    assert health["reachable"] is True
    assert health["model_present"] is False
    assert health["ok"] is False


def test_health_check_ok_when_model_present():
    body = json.dumps({"models": [{"name": "qwen2.5:7b-instruct"}]}).encode("utf-8")
    provider = LocalAIProvider()
    with patch("urllib.request.urlopen", return_value=_FakeHTTPResponse(body)):
        health = provider.health_check()
    assert health["ok"] is True


def test_assert_ready_raises_model_missing_before_a_long_run():
    body = json.dumps({"models": [{"name": "something-else:latest"}]}).encode("utf-8")
    provider = LocalAIProvider()
    with patch("urllib.request.urlopen", return_value=_FakeHTTPResponse(body)):
        with pytest.raises(ModelMissing):
            provider.assert_ready()


def test_customer_messages_never_leak_technical_detail():
    """Paragraph 29: customers get plain language, not ConnectionError dumps."""
    for exc_cls in (ProviderUnavailable, ModelMissing, ProviderTimeout, MalformedResponse):
        msg = exc_cls.customer_message
        for leak in ("HTTPConnectionPool", "11434", "Traceback", "urllib", "ollama"):
            assert leak.lower() not in msg.lower()


# ---------------------------------------------------- no silent paid fallback ---


def test_local_failure_does_not_fall_back_to_openai():
    """The single most important cost guarantee in the pilot."""
    called = {"openai": False}

    def _boom(*_a, **_k):
        called["openai"] = True
        raise AssertionError("OpenAI must not be called as a silent fallback")

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")), \
            patch("ai_client.get_client", side_effect=_boom):
        with pytest.raises(ProviderUnavailable):
            ai_providers.generate("sys", "user", 64, task="chapter")

    assert called["openai"] is False


def test_chat_with_task_routes_local_without_touching_openai():
    def _boom(*_a, **_k):
        raise AssertionError("OpenAI must not be called for a local chapter task")

    with patch("urllib.request.urlopen", return_value=_FakeHTTPResponse(
            _ollama_chat_body("local text"))), patch("ai_client.get_client", side_effect=_boom):
        out = ai_client.chat("sys", "user", 256, task="chapter")

    assert out == "local text"


def test_chat_with_meta_reports_zero_billable_for_local():
    with patch("urllib.request.urlopen", return_value=_FakeHTTPResponse(
            _ollama_chat_body("local text"))):
        result = ai_client.chat_with_meta("sys", "user", 256, task="chapter")

    assert result.billable_calls == 0
    assert result.provider == "local"


# --------------------------------------------------------------- registry ---


def test_registered_models_have_context_for_real_chapter_prompts():
    """Paragraph 12: a 12k-char prior-body slice must not be silently truncated."""
    for spec in ai_providers.MODEL_REGISTRY.values():
        assert spec.context_tokens >= 16000, f"{spec.model_id} context too small for chapters"


def test_get_model_exists_on_ai_client():
    """Regression: two vision-QC modules import this name."""
    assert ai_client.get_model() == ai_client.MODEL
