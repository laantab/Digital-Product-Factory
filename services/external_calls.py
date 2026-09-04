"""Central fail-closed guard for outbound paid/external calls.

WHY
---
FACTORY_TEST_MODE was only enforced at scattered call sites. Research, titles
and outlines each had their own offline branch, but chapter generation did not,
so Safe Mode would happily spend real money on an OpenAI call whenever a valid
key happened to be loaded. Blanking keys in the launcher helped, but that is a
convention, not a guarantee -- one launcher that forgets, or one key present in
the OS environment, and money leaves the account.

This module is the guarantee. It is checked at the few places where a request
can actually leave the process:

    ai_client.get_client            OpenAI text + image generation
    ebook_research_engine           Tavily topic search
    market_research                 Tavily research context (pre-existing check)
    ebook_pexels._http_get          Pexels stock photos (pre-existing check)

Fail-closed means the default is "no". If the mode cannot be determined, or the
guard is reached at all in test mode, the call is refused rather than attempted.

ExternalCallBlocked subclasses RuntimeError so existing broad handlers continue
to behave exactly as before.
"""
from __future__ import annotations

import os

#: What a customer may see. Never mentions keys, env vars, providers or models.
CUSTOMER_MESSAGE = "Factory AI could not start. Please try again."


class ExternalCallBlocked(RuntimeError):
    """An outbound paid/external call was refused by the spend guard."""

    customer_message = CUSTOMER_MESSAGE

    def __init__(self, service: str, detail: str = ""):
        self.service = service
        self.detail = detail or f"Outbound {service} call blocked (FACTORY_TEST_MODE=1)"
        super().__init__(self.detail)


def external_calls_blocked() -> bool:
    """True when no outbound paid/external call may be made."""
    return str(os.environ.get("FACTORY_TEST_MODE") or "") == "1"


def assert_external_call_allowed(service: str) -> None:
    """Refuse an outbound call in Safe Mode. Call immediately before the request.

    ``service`` is for the private log only -- it is never shown to a customer.
    """
    if external_calls_blocked():
        raise ExternalCallBlocked(service)


# ---------------------------------------------------------------------------
# Ebook fixture mode (test-only deterministic content)
# ---------------------------------------------------------------------------

_TRUE_VALUES = frozenset({"1", "true", "yes"})


def _is_true(raw: object) -> bool:
    """Strictly true. Anything absent, blank, malformed or unexpected is false."""
    return str(raw or "").strip().lower() in _TRUE_VALUES


def ebook_fixture_mode() -> bool:
    """Whether the Ebook path may serve deterministic test fixture content.

    DUAL-GATED ON PURPOSE. Fixture content is not a product; a customer must
    never receive it. Requiring two independent switches means a single stray
    environment variable -- one leftover export, one mis-set service config --
    cannot put fixture content in front of a paying customer:

        FACTORY_TEST_MODE=1             the process is a test/Safe Mode process
        EBOOK_CUSTOMER_PATH_FIXTURE=1   this run wants fixture content

    Fail-closed: if either value is missing, blank, "0", "false", or anything
    unrecognised, the normal production path is used. There is deliberately no
    silent fallback to fixture content.

    Scope: the Ebook workspace only. No other product builder consults this.
    """
    return _is_true(os.environ.get("FACTORY_TEST_MODE")) and _is_true(
        os.environ.get("EBOOK_CUSTOMER_PATH_FIXTURE")
    )
