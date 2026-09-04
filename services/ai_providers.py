"""Provider-neutral text generation for the Factory.

WHY THIS EXISTS
---------------
Business logic should not know or care whether text came from OpenAI or from a
local engine. Before this module, every text call went straight to OpenAI via
``ai_client.chat``/``chat_json``. This module introduces a provider boundary so
the ebook workflow can be pointed at a local engine without any call site
learning about it.

SCOPE (Local Manuscript Pilot)
------------------------------
Only two tasks are eligible for local generation right now:

    chapter          - writing one ebook chapter
    chapter_repair   - repairing one ebook chapter that failed the quality gate

Every other AI task in the Factory keeps its existing OpenAI behaviour, byte for
byte. A call that passes no ``task`` is treated as "legacy OpenAI" and routed
exactly as it was before this module existed.

TWO DIFFERENT IDEAS OF "COST"
-----------------------------
Kept deliberately separate so pricing can be improved later without touching
generation:

  * ``billable_calls``  - how many calls the Factory's own meter should charge
                          for. A local call is 0. This is what feeds the
                          customer-facing ledger.
  * actual vendor cost  - what a provider really bills. The Factory does NOT
                          measure this today (there is no token accounting
                          anywhere), so no code here pretends to know it.

A local generation is therefore "$0 billable" - a statement about the Factory's
administered price, not a measurement of electricity or hardware.

NO SILENT PAID FALLBACK
-----------------------
If a pilot task is routed local and local fails - unavailable, missing model,
malformed output, timeout, or a failed quality gate upstream - this module
raises. It never quietly falls back to a paid provider. Escalating to a paid
provider is a decision for the caller and the customer, never a side effect.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# Task identifiers
# --------------------------------------------------------------------------

TASK_CHAPTER = "chapter"
TASK_CHAPTER_REPAIR = "chapter_repair"

#: Tasks the pilot is allowed to run locally. Intentionally small.
LOCAL_PILOT_TASKS = frozenset({TASK_CHAPTER, TASK_CHAPTER_REPAIR})

# --------------------------------------------------------------------------
# Policy
# --------------------------------------------------------------------------

POLICY_LOCAL_ONLY = "local_only"
POLICY_LOCAL_FIRST = "local_first"
POLICY_PREMIUM = "premium"

_VALID_POLICIES = (POLICY_LOCAL_ONLY, POLICY_LOCAL_FIRST, POLICY_PREMIUM)

DEFAULT_POLICY = POLICY_LOCAL_FIRST


def get_policy() -> str:
    """Active generation policy. Unknown values fall back to the safe default."""
    raw = str(os.environ.get("FACTORY_AI_POLICY") or "").strip().lower()
    return raw if raw in _VALID_POLICIES else DEFAULT_POLICY


# --------------------------------------------------------------------------
# Model registry (paragraph 23: quality must not depend on a random model)
# --------------------------------------------------------------------------

STATUS_APPROVED = "approved"
STATUS_EXPERIMENTAL = "experimental"
STATUS_DEPRECATED = "deprecated"


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    provider: str
    min_ram_gb: float
    recommended_ram_gb: float
    disk_gb: float
    context_tokens: int
    supported_tasks: frozenset
    status: str
    #: Licence of the model weights. Recorded because bundling weights into a
    #: commercial installer is a licensing decision, not just an engineering one.
    license: str = "unknown"
    #: True for models that emit <think> reasoning blocks (Qwen3 family).
    #: Those blocks must never reach a manuscript.
    thinking: bool = False


#: Local models the Factory has actually been exercised against.
MODEL_REGISTRY: dict[str, ModelSpec] = {
    "qwen3:8b": ModelSpec(
        model_id="qwen3:8b",
        provider="local",
        min_ram_gb=8.0,
        recommended_ram_gb=16.0,
        disk_gb=5.2,
        context_tokens=40960,
        supported_tasks=frozenset(LOCAL_PILOT_TASKS),
        status=STATUS_EXPERIMENTAL,
        license="Apache-2.0",
        thinking=True,
    ),
    "qwen2.5:7b-instruct": ModelSpec(
        model_id="qwen2.5:7b-instruct",
        provider="local",
        min_ram_gb=8.0,
        recommended_ram_gb=16.0,
        disk_gb=4.7,
        context_tokens=32768,
        supported_tasks=frozenset(LOCAL_PILOT_TASKS),
        status=STATUS_EXPERIMENTAL,
        license="Apache-2.0",
    ),
    "qwen2.5:14b-instruct": ModelSpec(
        model_id="qwen2.5:14b-instruct",
        provider="local",
        min_ram_gb=16.0,
        recommended_ram_gb=32.0,
        disk_gb=9.0,
        context_tokens=32768,
        supported_tasks=frozenset(LOCAL_PILOT_TASKS),
        status=STATUS_EXPERIMENTAL,
        license="Apache-2.0",
    ),
    "llama3.1:8b": ModelSpec(
        model_id="llama3.1:8b",
        provider="local",
        min_ram_gb=8.0,
        recommended_ram_gb=16.0,
        disk_gb=4.7,
        context_tokens=131072,
        supported_tasks=frozenset(LOCAL_PILOT_TASKS),
        status=STATUS_EXPERIMENTAL,
        # Not Apache. Community licence with redistribution conditions --
        # check before ever bundling these weights in a paid product.
        license="Llama-3.1-Community",
    ),
}

DEFAULT_LOCAL_MODEL = "qwen3:8b"


def get_local_model() -> str:
    return str(os.environ.get("FACTORY_LOCAL_AI_MODEL") or DEFAULT_LOCAL_MODEL).strip()


def get_local_base_url() -> str:
    url = str(os.environ.get("FACTORY_LOCAL_AI_URL") or "").strip()
    return url.rstrip("/") if url else "http://127.0.0.1:11434"


def get_local_timeout() -> float:
    try:
        return max(5.0, float(os.environ.get("FACTORY_LOCAL_AI_TIMEOUT") or 600))
    except (TypeError, ValueError):
        return 600.0


# --------------------------------------------------------------------------
# Errors - typed so callers and tests can distinguish failure modes
# --------------------------------------------------------------------------


class ProviderError(RuntimeError):
    """Base class. Carries a customer-safe message plus technical detail."""

    customer_message = "Factory AI could not complete this step."

    def __init__(self, detail: str = "", customer_message: str | None = None):
        self.detail = detail or ""
        if customer_message:
            self.customer_message = customer_message
        super().__init__(detail or self.customer_message)


class ProviderUnavailable(ProviderError):
    customer_message = "Factory AI could not start. Try Again."


class ModelMissing(ProviderError):
    customer_message = "Factory AI needs its writing model before it can create this product."


class ProviderTimeout(ProviderError):
    customer_message = "Factory AI took too long to respond. Try Again."


class MalformedResponse(ProviderError):
    customer_message = "Factory AI returned an unreadable response. Try Again."


# --------------------------------------------------------------------------
# Result
# --------------------------------------------------------------------------


_THINK_BLOCK = re.compile(r"<think\b[^>]*>.*?</think\s*>", re.DOTALL | re.IGNORECASE)
_ORPHAN_THINK = re.compile(r"^\s*<think\b[^>]*>.*?(?=\n\s*\n|\Z)", re.DOTALL | re.IGNORECASE)


def strip_thinking(text: str) -> str:
    """Remove <think> reasoning blocks from model output.

    Belt and braces alongside the ``think: false`` request. A reasoning block
    that leaked into a manuscript would be a visible defect in a product the
    customer sells, so it is removed here rather than relied upon not to appear.
    """
    if not text:
        return ""
    cleaned = _THINK_BLOCK.sub("", text)
    if "<think" in cleaned.lower():
        # Unclosed block (truncated output): drop from the tag onward.
        cleaned = _ORPHAN_THINK.sub("", cleaned)
        cleaned = re.sub(r"</?think\s*>", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


@dataclass
class ProviderResult:
    """One generation. ``billable_calls`` is what the Factory meter charges for."""

    text: str
    provider: str
    model: str
    billable_calls: int = 0
    meta: dict = field(default_factory=dict)


# --------------------------------------------------------------------------
# Provider interface
# --------------------------------------------------------------------------


class AIProvider:
    name = "base"
    billable = True

    def generate_text(self, system: str, user: str, max_tokens: int) -> ProviderResult:
        raise NotImplementedError

    def health_check(self) -> dict:
        raise NotImplementedError

    def capabilities(self) -> dict:
        return {"text": True, "json_mode": False, "images": False}

    def model_info(self) -> dict:
        return {"model": "", "provider": self.name, "context_tokens": 0}

    def estimate_cost(self, task: str) -> float:
        """Factory administered price for one call of this task. Not vendor cost."""
        return 0.0

    def supports_task(self, task: str) -> bool:
        return True


class OpenAIProvider(AIProvider):
    """The existing behaviour, unchanged, wrapped in the provider interface."""

    name = "openai"
    billable = True

    def generate_text(self, system: str, user: str, max_tokens: int) -> ProviderResult:
        from ai_client import MODEL, get_client  # late import: avoids a cycle

        client = get_client()
        resp = client.chat.completions.create(
            model=MODEL,
            max_completion_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        text = (resp.choices[0].message.content or "").strip()
        return ProviderResult(text=text, provider=self.name, model=MODEL, billable_calls=1)

    def health_check(self) -> dict:
        from ai_client import MODEL, _get_key_and_source, _is_placeholder_key

        key, source = _get_key_and_source()
        ready = bool(key and key.strip() and not _is_placeholder_key(key))
        return {
            "ok": ready,
            "provider": self.name,
            "model": MODEL,
            "reachable": ready,
            "model_present": ready,
            "key_source": source,
            "error": "" if ready else "API key missing or placeholder",
        }

    def capabilities(self) -> dict:
        return {"text": True, "json_mode": True, "images": True}

    def model_info(self) -> dict:
        from ai_client import MODEL

        return {"model": MODEL, "provider": self.name, "context_tokens": 0}


class LocalAIProvider(AIProvider):
    """Local engine speaking the Ollama HTTP API.

    Customer-facing name is "Factory AI". The engine is an internal detail and
    must never be surfaced in the normal product workflow.
    """

    name = "local"
    billable = False

    def __init__(self, base_url: str | None = None, model: str | None = None,
                 timeout: float | None = None):
        self.base_url = (base_url or get_local_base_url()).rstrip("/")
        self.model = model or get_local_model()
        self.timeout = timeout if timeout is not None else get_local_timeout()

    # -- transport ---------------------------------------------------------

    def _post(self, path: str, payload: dict, timeout: float | None = None) -> dict:
        url = f"{self.base_url}{path}"
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            detail = f"HTTP {exc.code} from local engine at {url}"
            if exc.code == 404:
                raise ModelMissing(detail) from exc
            raise ProviderUnavailable(detail) from exc
        except TimeoutError as exc:
            raise ProviderTimeout(f"Local engine timed out after {timeout or self.timeout}s") from exc
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, TimeoutError):
                raise ProviderTimeout(f"Local engine timed out: {reason}") from exc
            raise ProviderUnavailable(f"Local engine unreachable at {url}: {reason}") from exc
        except OSError as exc:
            raise ProviderUnavailable(f"Local engine unreachable at {url}: {exc}") from exc

        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise MalformedResponse(f"Local engine returned non-JSON: {raw[:200]!r}") from exc
        if not isinstance(parsed, dict):
            raise MalformedResponse(f"Local engine returned {type(parsed).__name__}, expected object")
        return parsed

    def _get(self, path: str, timeout: float | None = None) -> dict:
        url = f"{self.base_url}{path}"
        try:
            with urllib.request.urlopen(url, timeout=timeout or 10) as resp:
                raw = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            raise ProviderUnavailable(f"HTTP {exc.code} from local engine at {url}") from exc
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise ProviderUnavailable(f"Local engine unreachable at {url}: {exc}") from exc
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise MalformedResponse(f"Local engine returned non-JSON: {raw[:200]!r}") from exc
        return parsed if isinstance(parsed, dict) else {}

    # -- interface ---------------------------------------------------------

    def installed_models(self) -> list[str]:
        data = self._get("/api/tags")
        out = []
        for entry in data.get("models") or []:
            if isinstance(entry, dict) and entry.get("name"):
                out.append(str(entry["name"]))
        return out

    def _model_installed(self, installed: list[str]) -> bool:
        """Ollama reports 'name:tag'; accept an exact match or a bare-name match."""
        wanted = self.model.strip()
        if wanted in installed:
            return True
        base = wanted.split(":", 1)[0]
        return any(m == wanted or m.split(":", 1)[0] == base for m in installed)

    def health_check(self) -> dict:
        info = {
            "ok": False,
            "provider": self.name,
            "model": self.model,
            "reachable": False,
            "model_present": False,
            "models": [],
            "error": "",
            "customer_message": "",
        }
        try:
            installed = self.installed_models()
        except ProviderError as exc:
            info["error"] = exc.detail
            info["customer_message"] = exc.customer_message
            return info

        info["reachable"] = True
        info["models"] = installed
        if not self._model_installed(installed):
            info["error"] = f"model {self.model!r} not installed (have: {installed or 'none'})"
            info["customer_message"] = ModelMissing.customer_message
            return info

        info["model_present"] = True
        info["ok"] = True
        return info

    def assert_ready(self) -> None:
        """Raise before a long run rather than failing halfway through a book."""
        health = self.health_check()
        if health["ok"]:
            return
        if not health["reachable"]:
            raise ProviderUnavailable(health["error"] or "local engine unreachable")
        raise ModelMissing(health["error"] or f"model {self.model!r} not installed")

    def generate_text(self, system: str, user: str, max_tokens: int) -> ProviderResult:
        spec = MODEL_REGISTRY.get(self.model)
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {"num_predict": int(max_tokens)},
        }
        # Qwen3-family models reason out loud inside <think> blocks. Prose for a
        # book must never contain them, so ask the engine to skip thinking. Only
        # sent for models the registry marks as thinking-capable, because other
        # models reject the field.
        if spec is not None and spec.thinking:
            payload["think"] = False

        data = self._post("/api/chat", payload)

        if data.get("error"):
            detail = str(data.get("error"))
            if "not found" in detail.lower() or "pull" in detail.lower():
                raise ModelMissing(detail)
            raise ProviderUnavailable(detail)

        message = data.get("message")
        if not isinstance(message, dict):
            raise MalformedResponse(f"missing 'message' object in response: {str(data)[:200]!r}")
        text = message.get("content")
        if not isinstance(text, str):
            raise MalformedResponse(f"'message.content' was {type(text).__name__}, expected str")
        text = strip_thinking(text)
        if not text:
            raise MalformedResponse("local engine returned empty content")

        return ProviderResult(
            text=text,
            provider=self.name,
            model=self.model,
            billable_calls=0,  # local generation is never charged by the Factory meter
            meta={"done_reason": data.get("done_reason", "")},
        )

    def capabilities(self) -> dict:
        # json_mode False on purpose: the pilot routes plain-text chapter calls
        # only. Structured-JSON parity is out of scope and unproven here.
        return {"text": True, "json_mode": False, "images": False}

    def model_info(self) -> dict:
        spec = MODEL_REGISTRY.get(self.model)
        return {
            "model": self.model,
            "provider": self.name,
            "context_tokens": spec.context_tokens if spec else 0,
            "status": spec.status if spec else "unregistered",
        }

    def estimate_cost(self, task: str) -> float:
        return 0.0

    def supports_task(self, task: str) -> bool:
        return task in LOCAL_PILOT_TASKS


# --------------------------------------------------------------------------
# Selection
# --------------------------------------------------------------------------

_local_singleton: LocalAIProvider | None = None
_openai_singleton: OpenAIProvider | None = None


def get_local_provider() -> LocalAIProvider:
    global _local_singleton
    if _local_singleton is None:
        _local_singleton = LocalAIProvider()
    return _local_singleton


def get_openai_provider() -> OpenAIProvider:
    global _openai_singleton
    if _openai_singleton is None:
        _openai_singleton = OpenAIProvider()
    return _openai_singleton


def reset_providers() -> None:
    """Drop cached providers so env changes take effect. Used by tests."""
    global _local_singleton, _openai_singleton
    _local_singleton = None
    _openai_singleton = None


def routes_local(task: str | None) -> bool:
    """True when this task should be generated locally.

    A task of ``None`` means a legacy call site that predates the provider
    boundary. Those always stay on OpenAI so existing behaviour is unchanged.

    Under FACTORY_TEST_MODE nothing routes local. The Factory's test contract is
    that no provider is contacted at all, and a local engine is still a
    provider: because it listens on this machine it is reachable from the test
    suite, so without this guard an automated test would silently perform a real
    generation. Tests inject their own chapter function explicitly instead.
    """
    if str(os.environ.get("FACTORY_TEST_MODE") or "") == "1":
        return False
    if not task or task not in LOCAL_PILOT_TASKS:
        return False
    return get_policy() in (POLICY_LOCAL_ONLY, POLICY_LOCAL_FIRST)


def select_provider(task: str | None) -> AIProvider:
    return get_local_provider() if routes_local(task) else get_openai_provider()


def generate(system: str, user: str, max_tokens: int, task: str | None = None) -> ProviderResult:
    """Route one text generation.

    Pilot tasks go local and, on failure, RAISE. They are never silently
    retried against a paid provider - that is the caller's decision to make.
    """
    provider = select_provider(task)
    return provider.generate_text(system, user, max_tokens)


def factory_ai_status() -> dict:
    """Customer-safe status for both providers. Never includes secrets."""
    local = get_local_provider().health_check()
    openai_health = get_openai_provider().health_check()
    return {
        "policy": get_policy(),
        "pilot_tasks": sorted(LOCAL_PILOT_TASKS),
        "factory_ai": {
            "ready": bool(local.get("ok")),
            "message": local.get("customer_message") or ("Factory AI is ready." if local.get("ok") else "Factory AI is not ready."),
            "model": local.get("model"),
            "detail": local.get("error"),
        },
        "premium_ai": {
            "ready": bool(openai_health.get("ok")),
            "model": openai_health.get("model"),
        },
    }
