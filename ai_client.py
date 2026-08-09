"""Shared OpenAI client.

Uses Replit's managed AI Integrations proxy, which is OpenAI-compatible. This
means no personal OpenAI API key is required — the proxy credentials are
provisioned into the environment automatically.
"""
import json
import os

from dotenv import load_dotenv
from openai import OpenAI

_client = None
_key_source = ""
_base_url_source = ""

# Load .env on module import if not already loaded
load_dotenv()

# General-purpose model. gpt-5 family: temperature is fixed at 1 and
# `max_completion_tokens` is used instead of `max_tokens`.
MODEL = "gpt-5.4"

# Placeholder patterns that indicate a non-functional key
_PLACEHOLDER_PREFIXES = (
    "your_", "paste_your", "replace_this", "placeholder",
    "your_key_here", "your_api_key_here",
)


def _is_placeholder_key(key: str) -> bool:
    k = (key or "").strip().lower()
    return any(k.startswith(p) or k == p for p in _PLACEHOLDER_PREFIXES)


def _get_key_and_source() -> tuple[str, str]:
    """Return (api_key, source_var_name)."""
    # Priority: AI_INTEGRATIONS_* first, then OPENAI_*
    key = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY", "")
    if key and key.strip() and not _is_placeholder_key(key):
        return key, "AI_INTEGRATIONS_OPENAI_API_KEY"
    key = os.environ.get("OPENAI_API_KEY", "")
    if key and key.strip() and not _is_placeholder_key(key):
        return key, "OPENAI_API_KEY"
    return os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY", ""), "AI_INTEGRATIONS_OPENAI_API_KEY"


def _get_base_url_and_source() -> tuple[str, str]:
    """Return (base_url, source_var_name)."""
    url = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL", "")
    if url and url.strip():
        return url, "AI_INTEGRATIONS_OPENAI_BASE_URL"
    url = os.environ.get("OPENAI_BASE_URL", "")
    if url and url.strip():
        return url, "OPENAI_BASE_URL"
    return "https://api.openai.com/v1", "default"


def get_key_source() -> str:
    """Return the env var name the active key came from."""
    _, src = _get_key_and_source()
    return src


def get_base_url_source() -> str:
    """Return the env var name the active base URL came from."""
    _, src = _get_base_url_and_source()
    return src


def get_client() -> OpenAI:
    global _client, _key_source, _base_url_source
    if _client is None:
        api_key, _key_source = _get_key_and_source()
        base_url, _base_url_source = _get_base_url_and_source()
        if not api_key or not api_key.strip() or _is_placeholder_key(api_key):
            raise RuntimeError(
                "AI is not configured. The API key env var is missing or contains a placeholder."
            )
        if not base_url or not base_url.strip():
            base_url = "https://api.openai.com/v1"
            _base_url_source = "default"
        _client = OpenAI(base_url=base_url, api_key=api_key)
    return _client


def chat(system: str, user: str, max_completion_tokens: int = 8192) -> str:
    """Run a single-turn chat completion and return the text content."""
    client = get_client()
    resp = client.chat.completions.create(
        model=MODEL,
        max_completion_tokens=max_completion_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        # Strip a ```json ... ``` fence if the model added one.
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    return json.loads(text.strip())


def chat_json(system: str, user: str, max_completion_tokens: int = 4096) -> dict:
    """Single-turn chat that returns a parsed JSON object."""
    client = get_client()
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            max_completion_tokens=max_completion_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return _parse_json(resp.choices[0].message.content or "")
    except Exception:
        # Fallback for proxies/models that reject response_format: ask plainly
        # and parse the JSON out of the text.
        text = chat(system, user + "\n\nReturn ONLY valid JSON.", max_completion_tokens)
        return _parse_json(text)
