"""Stripe and Lemon Squeezy clients, plus webhook signature verification.

Deliberately built on `requests` rather than each vendor's SDK. The Factory
needs three things from a payment provider — start a checkout, verify a
webhook, read a subscription — and two more runtime dependencies to get them
is a poor trade for a release gate that must stay green offline.

Nothing here reads a price. Amounts come from `plans.py`, are sent to the
provider, and are checked again on the way back, so a price edited in a
provider dashboard can never quietly become what a customer is charged.

No key is ever logged, echoed in an error, or returned to the browser.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any

import requests

STRIPE = "stripe"
LEMON_SQUEEZY = "lemon_squeezy"
PROVIDERS = (STRIPE, LEMON_SQUEEZY)

STRIPE_API = "https://api.stripe.com/v1"
LEMON_API = "https://api.lemonsqueezy.com/v1"

_TIMEOUT = 20
# Stripe rejects a signature whose timestamp is far from now; this is the same
# tolerance the official libraries use.
WEBHOOK_TOLERANCE_SECONDS = 300


class BillingConfigError(RuntimeError):
    """A provider was asked to do something before it was configured."""


class BillingProviderError(RuntimeError):
    """The provider rejected the request."""


class WebhookVerificationError(RuntimeError):
    """A webhook did not carry a valid signature. Never trust its contents."""


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    configured: bool
    mode: str = "unset"          # "live", "test", or "unset"
    missing: tuple[str, ...] = ()


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
def stripe_config() -> ProviderConfig:
    key = _env("STRIPE_SECRET_KEY")
    missing = [n for n in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET")
               if not _env(n)]
    mode = "unset"
    if key.startswith("sk_live_"):
        mode = "live"
    elif key.startswith("sk_test_"):
        mode = "test"
    return ProviderConfig(STRIPE, not missing, mode, tuple(missing))


def lemon_config() -> ProviderConfig:
    missing = [n for n in ("LEMONSQUEEZY_API_KEY", "LEMONSQUEEZY_STORE_ID",
                           "LEMONSQUEEZY_WEBHOOK_SECRET") if not _env(n)]
    mode = "live" if _env("LEMONSQUEEZY_API_KEY") else "unset"
    return ProviderConfig(LEMON_SQUEEZY, not missing, mode, tuple(missing))


def provider_config(provider: str) -> ProviderConfig:
    if provider == STRIPE:
        return stripe_config()
    if provider == LEMON_SQUEEZY:
        return lemon_config()
    raise ValueError(f"Unknown payment provider: {provider!r}")


def configured_providers() -> list[str]:
    return [p for p in PROVIDERS if provider_config(p).configured]


def status_report() -> dict[str, Any]:
    """What the account settings screen shows. Never includes a key."""
    out: dict[str, Any] = {"providers": {}, "any_configured": False}
    for p in PROVIDERS:
        cfg = provider_config(p)
        out["providers"][p] = {
            "configured": cfg.configured,
            "mode": cfg.mode,
            "missing_env": list(cfg.missing),
        }
        out["any_configured"] = out["any_configured"] or cfg.configured
    return out


# --------------------------------------------------------------------------- #
# Price id mapping
# --------------------------------------------------------------------------- #
def price_env_name(provider: str, plan_id: str, period: str) -> str:
    prefix = "STRIPE_PRICE" if provider == STRIPE else "LEMONSQUEEZY_VARIANT"
    return f"{prefix}_{plan_id.upper()}_{period.upper()}"


def provider_price_id(provider: str, plan_id: str, period: str) -> str:
    name = price_env_name(provider, plan_id, period)
    value = _env(name)
    if not value:
        raise BillingConfigError(
            f"{name} is not set. Create the price in the provider dashboard "
            f"(or run scripts/setup_billing_products.py) and put its id in .env."
        )
    return value


# --------------------------------------------------------------------------- #
# Stripe
# --------------------------------------------------------------------------- #
def _stripe_request(method: str, path: str, data: dict | None = None,
                    idempotency_key: str = "") -> dict[str, Any]:
    cfg = stripe_config()
    if not _env("STRIPE_SECRET_KEY"):
        raise BillingConfigError(
            "STRIPE_SECRET_KEY is not set; Stripe checkout is unavailable.")
    headers = {"Authorization": f"Bearer {_env('STRIPE_SECRET_KEY')}"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    try:
        resp = requests.request(
            method, f"{STRIPE_API}{path}", data=data or {},
            headers=headers, timeout=_TIMEOUT)
    except requests.RequestException as exc:
        raise BillingProviderError(f"Could not reach Stripe: {exc}") from exc
    try:
        body = resp.json()
    except ValueError:
        raise BillingProviderError(
            f"Stripe returned a non-JSON response ({resp.status_code}).")
    if resp.status_code >= 400:
        message = (body.get("error") or {}).get("message") or "unknown error"
        raise BillingProviderError(f"Stripe rejected the request: {message}")
    return body


def stripe_price(price_id: str) -> dict[str, Any]:
    return _stripe_request("GET", f"/prices/{price_id}")


def stripe_create_checkout(
    *, price_id: str, success_url: str, cancel_url: str,
    client_reference_id: str, customer_email: str = "",
    metadata: dict[str, str] | None = None,
    idempotency_key: str = "",
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "mode": "subscription",
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": 1,
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": client_reference_id,
        "allow_promotion_codes": "true",
    }
    if customer_email:
        data["customer_email"] = customer_email
    for key, value in (metadata or {}).items():
        data[f"metadata[{key}]"] = str(value)
        data[f"subscription_data[metadata][{key}]"] = str(value)
    return _stripe_request(
        "POST", "/checkout/sessions", data, idempotency_key=idempotency_key)


def verify_stripe_webhook(payload: bytes, signature_header: str,
                          secret: str = "", tolerance: int = WEBHOOK_TOLERANCE_SECONDS,
                          now: float | None = None) -> dict[str, Any]:
    """Verify `Stripe-Signature` and return the parsed event.

    An unverified webhook is an anonymous stranger claiming somebody paid, so
    failure raises rather than returning a "probably fine" flag.
    """
    secret = secret or _env("STRIPE_WEBHOOK_SECRET")
    if not secret:
        raise BillingConfigError("STRIPE_WEBHOOK_SECRET is not set.")
    if not signature_header:
        raise WebhookVerificationError("Missing Stripe-Signature header.")

    parts: dict[str, list[str]] = {}
    for chunk in str(signature_header).split(","):
        key, _, value = chunk.strip().partition("=")
        parts.setdefault(key, []).append(value)
    timestamps = parts.get("t") or []
    signatures = parts.get("v1") or []
    if not timestamps or not signatures:
        raise WebhookVerificationError("Malformed Stripe-Signature header.")

    try:
        timestamp = int(timestamps[0])
    except ValueError:
        raise WebhookVerificationError("Malformed timestamp in Stripe-Signature.")
    current = time.time() if now is None else now
    if tolerance and abs(current - timestamp) > tolerance:
        raise WebhookVerificationError(
            "Stripe webhook timestamp is outside the tolerance window.")

    signed = f"{timestamp}.".encode() + payload
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, s) for s in signatures):
        raise WebhookVerificationError("Stripe webhook signature did not match.")

    try:
        return json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise WebhookVerificationError(f"Stripe webhook body is not JSON: {exc}")


# --------------------------------------------------------------------------- #
# Lemon Squeezy
# --------------------------------------------------------------------------- #
def _lemon_request(method: str, path: str, payload: dict | None = None) -> dict[str, Any]:
    if not _env("LEMONSQUEEZY_API_KEY"):
        raise BillingConfigError(
            "LEMONSQUEEZY_API_KEY is not set; Lemon Squeezy checkout is unavailable.")
    headers = {
        "Authorization": f"Bearer {_env('LEMONSQUEEZY_API_KEY')}",
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
    }
    try:
        resp = requests.request(
            method, f"{LEMON_API}{path}",
            data=json.dumps(payload) if payload is not None else None,
            headers=headers, timeout=_TIMEOUT)
    except requests.RequestException as exc:
        raise BillingProviderError(f"Could not reach Lemon Squeezy: {exc}") from exc
    # DELETE (and some other calls) return 204 No Content on success -- there
    # is no body to parse, so don't try. Any other empty-body response is
    # only expected alongside an error status.
    if resp.status_code == 204 or not resp.content:
        if resp.status_code >= 400:
            raise BillingProviderError(
                f"Lemon Squeezy rejected the request ({resp.status_code}).")
        return {}
    try:
        body = resp.json()
    except ValueError:
        raise BillingProviderError(
            f"Lemon Squeezy returned a non-JSON response ({resp.status_code}).")
    if resp.status_code >= 400:
        errors = body.get("errors") or []
        message = (errors[0].get("detail") if errors else "") or "unknown error"
        raise BillingProviderError(f"Lemon Squeezy rejected the request: {message}")
    return body


def lemon_variant(variant_id: str) -> dict[str, Any]:
    return _lemon_request("GET", f"/variants/{variant_id}")


def lemon_create_checkout(
    *, variant_id: str, success_url: str, client_reference_id: str,
    customer_email: str = "", metadata: dict[str, str] | None = None,
) -> dict[str, Any]:
    store_id = _env("LEMONSQUEEZY_STORE_ID")
    if not store_id:
        raise BillingConfigError("LEMONSQUEEZY_STORE_ID is not set.")
    custom = {"account_ref": client_reference_id}
    custom.update({k: str(v) for k, v in (metadata or {}).items()})
    checkout_data: dict[str, Any] = {"custom": custom}
    # Lemon Squeezy validates checkout_data.email whenever the key is present,
    # even when its value is null -- "must be a valid email address" is
    # returned for a JSON null just as it would be for "not-an-email". Leaving
    # the key out entirely (rather than sending None) is what actually means
    # "let the customer type their own email on the hosted checkout page."
    if customer_email:
        checkout_data["email"] = customer_email
    payload = {
        "data": {
            "type": "checkouts",
            "attributes": {
                "checkout_data": checkout_data,
                "product_options": {"redirect_url": success_url},
            },
            "relationships": {
                "store": {"data": {"type": "stores", "id": str(store_id)}},
                "variant": {"data": {"type": "variants", "id": str(variant_id)}},
            },
        }
    }
    return _lemon_request("POST", "/checkouts", payload)


def verify_lemon_webhook(payload: bytes, signature_header: str,
                         secret: str = "") -> dict[str, Any]:
    """Verify `X-Signature` (HMAC-SHA256 hex of the raw body)."""
    secret = secret or _env("LEMONSQUEEZY_WEBHOOK_SECRET")
    if not secret:
        raise BillingConfigError("LEMONSQUEEZY_WEBHOOK_SECRET is not set.")
    if not signature_header:
        raise WebhookVerificationError("Missing X-Signature header.")
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, str(signature_header).strip()):
        raise WebhookVerificationError("Lemon Squeezy signature did not match.")
    try:
        return json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise WebhookVerificationError(
            f"Lemon Squeezy webhook body is not JSON: {exc}")
