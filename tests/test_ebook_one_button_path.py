"""Central spend guard and customer-safe error handling.

These protections stand on their own and are independent of ebook routing:

  * FACTORY_TEST_MODE must make an outbound paid call impossible, even when
    realistic-looking API keys are loaded. Key blanking in a launcher is a
    convention; this is the guarantee.
  * A customer must never see API keys, environment-variable names, provider or
    model names, tracebacks or raw exception text.

The ebook workspace ROUTING tests live separately and arrive with the routing
migration -- this file deliberately contains no routing expectations, so the
protection checkpoint can be verified and committed on its own.

No external call is made by any test here.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

import app as app_module
from services.external_calls import (
    ExternalCallBlocked,
    assert_external_call_allowed,
    external_calls_blocked,
)


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("FACTORY_TEST_MODE", "1")
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


# ------------------------------------------------- safe mode spend guard ---


def test_safe_mode_blocks_openai_even_with_a_realistic_key(monkeypatch):
    """Key blanking must not be the only protection."""
    monkeypatch.setenv("FACTORY_TEST_MODE", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-" + "a" * 40)
    monkeypatch.setenv("AI_INTEGRATIONS_OPENAI_API_KEY", "sk-proj-" + "b" * 40)

    import ai_client

    ai_client._client = None  # force a fresh build attempt
    with pytest.raises(ExternalCallBlocked):
        ai_client.get_client()


def test_safe_mode_blocks_tavily_even_with_a_realistic_key(monkeypatch):
    monkeypatch.setenv("FACTORY_TEST_MODE", "1")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-" + "c" * 32)

    from services.ebook_research_engine import _tavily_topic_search

    def _boom(*_a, **_k):
        raise AssertionError("Tavily must not be constructed in Safe Mode")

    with patch("tavily.TavilyClient", side_effect=_boom):
        live, ctx, urls = _tavily_topic_search("any topic", "any audience")
    assert live is False and ctx == "" and urls == []


def test_safe_mode_blocks_pexels_even_with_a_realistic_key(monkeypatch):
    monkeypatch.setenv("FACTORY_TEST_MODE", "1")
    monkeypatch.setenv("PEXELS_API_KEY", "d" * 56)

    from services.ebook_pexels import PexelsError, _http_get

    with pytest.raises(PexelsError):
        _http_get("https://api.pexels.com/v1/search?q=x", {})


def test_guard_is_fail_closed_and_reports_no_secrets():
    import os

    prior = os.environ.get("FACTORY_TEST_MODE")
    os.environ["FACTORY_TEST_MODE"] = "1"
    try:
        assert external_calls_blocked() is True
        with pytest.raises(ExternalCallBlocked) as err:
            assert_external_call_allowed("openai")
        assert "Factory AI could not start" in err.value.customer_message
        assert "sk-" not in str(err.value)
    finally:
        if prior is None:
            os.environ.pop("FACTORY_TEST_MODE", None)
        else:
            os.environ["FACTORY_TEST_MODE"] = prior


def test_guard_allows_calls_when_not_in_safe_mode(monkeypatch):
    """The guard must not block normal operation."""
    monkeypatch.delenv("FACTORY_TEST_MODE", raising=False)
    assert external_calls_blocked() is False
    assert_external_call_allowed("openai")  # must not raise


# --------------------------------------------- customer error wrapping ---


@pytest.mark.parametrize("raw", [
    "AI is not configured. The API key env var is missing or contains a placeholder.",
    "ConnectionError HTTPConnectionPool(host='localhost', port=11434)",
    "ModuleNotFoundError: No module named 'openai'",
    "KeyError: 'AI_INTEGRATIONS_OPENAI_API_KEY'",
    "model qwen3:8b not found, try pulling it",
    "Traceback (most recent call last): File app.py line 1",
])
def test_technical_errors_are_replaced_with_a_customer_message(raw):
    safe = app_module.customer_safe_message(RuntimeError(raw))
    assert safe == "Factory AI could not start. Please try again."
    low = safe.lower()
    for leak in ("api key", "env", "openai", "ollama", "11434", "traceback", "qwen"):
        assert leak not in low


def test_curated_customer_messages_are_kept():
    """Errors that already carry safe wording keep it."""
    from services.ai_providers import ModelMissing

    safe = app_module.customer_safe_message(ModelMissing("model qwen3:8b not installed"))
    assert "writing model" in safe.lower()
    assert "qwen" not in safe.lower()


def test_plain_business_messages_pass_through_unchanged():
    safe = app_module.customer_safe_message(ValueError("Please enter an ebook title."))
    assert safe == "Please enter an ebook title."


def test_empty_error_falls_back_to_the_customer_message():
    assert app_module.customer_safe_message(RuntimeError("")) == (
        "Factory AI could not start. Please try again."
    )


def test_generate_product_route_never_returns_a_raw_provider_error(client):
    """End to end through the real route: internals must not surface."""
    def _explode(*_a, **_k):
        raise RuntimeError(
            "AI is not configured. The API key env var is missing or contains a placeholder."
        )

    with patch("app.generate_product", side_effect=_explode):
        resp = client.post(
            "/generate-product",
            json={"product_type": "word_search", "fields": {"theme": "Animals"}},
        )
    assert resp.status_code == 500
    body = json.dumps(resp.get_json()).lower()
    assert "api key" not in body
    assert "env var" not in body
    assert "placeholder" not in body
    assert "factory ai could not start" in body
