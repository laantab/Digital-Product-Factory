"""Checkout orchestration and webhook handling.

The order of operations in `start_checkout` is the whole point of this module:

  1. Validate the plan and period against the catalog.
  2. For the Founder's Plan, claim a seat **before** talking to the provider.
     Reserving after a successful checkout means seat 101 has already paid.
  3. Ask the provider what it will charge, and refuse if it disagrees with the
     catalog.
  4. Create the checkout session.
  5. If anything after step 2 fails, give the seat back.

Webhooks only ever *confirm* what checkout already recorded. They never invent
a subscription from data a stranger posted, and every event is de-duplicated,
because providers deliver more than once by design.
"""
from __future__ import annotations

import os
import secrets
from typing import Any

from services.billing import plans as P
from services.billing import providers as PR
from services.billing import store as S


class CheckoutError(RuntimeError):
    """Checkout could not be started. The message is safe to show a customer."""


def _base_url() -> str:
    return (os.environ.get("FACTORY_PUBLIC_URL")
            or "http://127.0.0.1:5000").rstrip("/")


def new_account_ref() -> str:
    """Stable per-customer reference.

    The Factory has no user accounts yet, so this is a random opaque token the
    browser keeps. When real accounts land, this becomes the user id and
    nothing else in the billing layer has to change.
    """
    return "acct_" + secrets.token_urlsafe(18)


# --------------------------------------------------------------------------- #
# Read side
# --------------------------------------------------------------------------- #
def pricing_payload(account_ref: str = "") -> dict[str, Any]:
    remaining = S.founder_seats_remaining(P.FOUNDER_SEAT_LIMIT)
    payload = P.catalog(founder_seats_remaining=remaining)
    payload["providers"] = PR.status_report()
    payload["checkout_available"] = bool(PR.configured_providers())
    current = S.get_active_subscription(account_ref) if account_ref else None
    payload["current"] = subscription_payload(current)
    return payload


def subscription_payload(sub: dict[str, Any] | None) -> dict[str, Any]:
    """Never returns provider ids or anything a customer should not see."""
    if not sub:
        return {
            "plan_id": P.DEFAULT_PLAN_ID,
            "plan_name": P.get_plan(P.DEFAULT_PLAN_ID).name,
            "status": "none",
            "entitlements": P.entitlements(P.DEFAULT_PLAN_ID),
        }
    plan = P.get_plan(sub["plan_id"])
    return {
        "plan_id": plan.id,
        "plan_name": plan.name,
        "status": sub["status"],
        "billing_period": sub["billing_period"],
        "price_display": P.format_price(int(sub["price_cents"] or 0)),
        "current_period_end": sub.get("current_period_end") or "",
        "founder_seat": sub.get("founder_seat"),
        "price_locked_for_life": bool(sub.get("price_locked")),
        "entitlements": P.entitlements(plan.id),
    }


def usage_payload(account_ref: str) -> dict[str, Any]:
    sub = S.get_active_subscription(account_ref) if account_ref else None
    plan = P.get_plan(sub["plan_id"] if sub else P.DEFAULT_PLAN_ID)
    used = S.count_usage(account_ref) if account_ref else 0
    cap = plan.products_per_month
    return {
        "plan_id": plan.id,
        "period": S.current_period_key(),
        "products_used": used,
        "products_allowed": cap,
        "products_remaining": (max(0, cap - used) if cap >= 0 else -1),
        "over_limit": cap >= 0 and used >= cap,
    }


# --------------------------------------------------------------------------- #
# Checkout
# --------------------------------------------------------------------------- #
def _confirm_provider_price(provider: str, plan: P.Plan, period: str,
                            price_id: str) -> None:
    """Ask the provider what this price id actually costs, and compare.

    A price edited in a dashboard is the realistic way a customer ends up
    charged something nobody intended. If the provider cannot be reached the
    check is skipped rather than blocking checkout, but a genuine mismatch is
    always fatal.
    """
    try:
        if provider == PR.STRIPE:
            body = PR.stripe_price(price_id)
            amount = int(body.get("unit_amount") or 0)
            currency = str(body.get("currency") or "")
        else:
            body = PR.lemon_variant(price_id)
            attrs = (body.get("data") or {}).get("attributes") or {}
            amount = int(attrs.get("price") or 0)
            currency = str(attrs.get("currency") or P.CURRENCY)
    except PR.BillingProviderError:
        return  # Unreachable provider is handled by the checkout call itself.
    P.verify_provider_price(plan.id, period, amount, currency or P.CURRENCY)


def start_checkout(
    *, plan_id: str, billing_period: str, provider: str,
    account_ref: str, customer_email: str = "",
) -> dict[str, Any]:
    provider = str(provider or "").strip().lower()
    if provider not in PR.PROVIDERS:
        raise CheckoutError(f"Unknown payment provider: {provider!r}")
    cfg = PR.provider_config(provider)
    if not cfg.configured:
        raise CheckoutError(
            f"{provider} is not configured yet. Missing: {', '.join(cfg.missing)}.")

    try:
        plan = P.get_plan(plan_id)
    except ValueError as exc:
        raise CheckoutError(str(exc)) from exc

    period = str(billing_period or "").strip().lower()
    if not P.is_period_available(plan, period):
        raise CheckoutError(
            f"{plan.name} is not available on a {period or 'blank'} term.")
    if plan.id == P.FREE.id:
        raise CheckoutError("The Free plan does not require checkout.")
    if not account_ref:
        raise CheckoutError("An account reference is required to start checkout.")

    existing = S.get_active_subscription(account_ref)
    if existing and existing["plan_id"] == plan.id:
        raise CheckoutError(f"This account is already on {plan.name}.")

    price_cents = plan.price_cents(period)

    # 1. Claim the founding seat first. Reserving after payment succeeds is how
    #    a cohort of 100 quietly becomes a cohort of 104.
    subscription: dict[str, Any] | None = None
    if plan.limited_seats:
        try:
            subscription = S.reserve_founder_seat(
                account_ref=account_ref, provider=provider,
                billing_period=period, price_cents=price_cents,
                currency=P.CURRENCY, limit=plan.limited_seats,
                metadata={"plan_id": plan.id},
            )
        except S.SeatsSoldOutError as exc:
            raise CheckoutError(
                "The Founder's Plan is fully subscribed. All "
                f"{plan.limited_seats} founding seats have been taken."
            ) from exc
    else:
        subscription = S.create_pending_subscription(
            account_ref=account_ref, plan_id=plan.id, billing_period=period,
            provider=provider, price_cents=price_cents, currency=P.CURRENCY,
            metadata={"plan_id": plan.id},
        )

    try:
        price_id = PR.provider_price_id(provider, plan.id, period)
        _confirm_provider_price(provider, plan, period, price_id)

        success_url = f"{_base_url()}/?checkout=success&plan={plan.id}"
        cancel_url = f"{_base_url()}/?checkout=cancelled&plan={plan.id}"
        metadata = {
            "plan_id": plan.id,
            "billing_period": period,
            "subscription_row": str(subscription["id"]),
        }
        if subscription.get("founder_seat"):
            metadata["founder_seat"] = str(subscription["founder_seat"])

        if provider == PR.STRIPE:
            session = PR.stripe_create_checkout(
                price_id=price_id, success_url=success_url + "&session_id={CHECKOUT_SESSION_ID}",
                cancel_url=cancel_url, client_reference_id=account_ref,
                customer_email=customer_email, metadata=metadata,
                idempotency_key=f"factory-{subscription['id']}",
            )
            checkout_id = str(session.get("id") or "")
            checkout_url = str(session.get("url") or "")
        else:
            session = PR.lemon_create_checkout(
                variant_id=price_id, success_url=success_url,
                client_reference_id=account_ref,
                customer_email=customer_email, metadata=metadata)
            attrs = (session.get("data") or {}).get("attributes") or {}
            checkout_id = str((session.get("data") or {}).get("id") or "")
            checkout_url = str(attrs.get("url") or "")

        if not checkout_url:
            raise CheckoutError("The payment provider did not return a checkout link.")
        S.attach_checkout_id(subscription["id"], checkout_id)
    except Exception:
        # 5. Nothing was paid, so the seat goes back to the cohort immediately
        #    rather than waiting out the reservation window.
        S.release_founder_seat(subscription["id"])
        raise

    return {
        "checkout_url": checkout_url,
        "plan_id": plan.id,
        "plan_name": plan.name,
        "billing_period": period,
        "price_display": P.format_price(price_cents),
        "provider": provider,
        "founder_seat": subscription.get("founder_seat"),
        "seats_remaining": (
            S.founder_seats_remaining(plan.limited_seats)
            if plan.limited_seats else None
        ),
    }


# --------------------------------------------------------------------------- #
# Webhooks
# --------------------------------------------------------------------------- #
_STRIPE_ACTIVATE = {"checkout.session.completed"}
_STRIPE_CANCEL = {"customer.subscription.deleted"}
_STRIPE_UPDATE = {"customer.subscription.updated"}
_STRIPE_PAYMENT_FAILED = {"invoice.payment_failed"}

_LEMON_ACTIVATE = {"subscription_created", "subscription_resumed",
                   "subscription_unpaused"}
_LEMON_CANCEL = {"subscription_cancelled", "subscription_expired"}
_LEMON_PAST_DUE = {"subscription_payment_failed"}


def handle_stripe_event(event: dict[str, Any]) -> dict[str, Any]:
    """Apply one verified Stripe event. Safe to call twice with the same event."""
    event_id = str(event.get("id") or "")
    event_type = str(event.get("type") or "")
    if not S.record_event(provider=PR.STRIPE, event_id=event_id,
                          event_type=event_type, payload=event):
        return {"status": "duplicate", "event_type": event_type}

    obj = ((event.get("data") or {}).get("object")) or {}
    result: dict[str, Any] = {"status": "ignored", "event_type": event_type}

    if event_type in _STRIPE_ACTIVATE:
        updated = S.activate_subscription(
            checkout_id=str(obj.get("id") or ""),
            provider_subscription_id=str(obj.get("subscription") or ""),
            provider_customer_id=str(obj.get("customer") or ""),
        )
        result = {"status": "activated" if updated else "unmatched",
                  "event_type": event_type}
    elif event_type in _STRIPE_CANCEL:
        updated = S.set_subscription_status(
            provider_subscription_id=str(obj.get("id") or ""),
            status=S.STATUS_CANCELLED)
        result = {"status": "cancelled" if updated else "unmatched",
                  "event_type": event_type}
    elif event_type in _STRIPE_UPDATE:
        status = str(obj.get("status") or "")
        mapped = {
            "active": S.STATUS_ACTIVE,
            "past_due": S.STATUS_PAST_DUE,
            "unpaid": S.STATUS_PAST_DUE,
            "canceled": S.STATUS_CANCELLED,
        }.get(status)
        if mapped:
            period_end = obj.get("current_period_end")
            updated = S.set_subscription_status(
                provider_subscription_id=str(obj.get("id") or ""),
                status=mapped,
                current_period_end=str(period_end or ""))
            result = {"status": mapped if updated else "unmatched",
                      "event_type": event_type}
    elif event_type in _STRIPE_PAYMENT_FAILED:
        updated = S.set_subscription_status(
            provider_subscription_id=str(obj.get("subscription") or ""),
            status=S.STATUS_PAST_DUE)
        result = {"status": "past_due" if updated else "unmatched",
                  "event_type": event_type}

    S.mark_event_result(PR.STRIPE, event_id, result["status"])
    return result


def handle_lemon_event(event: dict[str, Any]) -> dict[str, Any]:
    """Apply one verified Lemon Squeezy event. Idempotent."""
    meta = event.get("meta") or {}
    event_type = str(meta.get("event_name") or "")
    data = event.get("data") or {}
    attrs = data.get("attributes") or {}
    event_id = str(meta.get("webhook_id") or data.get("id") or "")

    if not S.record_event(provider=PR.LEMON_SQUEEZY, event_id=event_id,
                          event_type=event_type, payload=event):
        return {"status": "duplicate", "event_type": event_type}

    custom = (meta.get("custom_data") or {})
    row_id = custom.get("subscription_row")
    subscription_id = int(row_id) if str(row_id or "").isdigit() else None
    result: dict[str, Any] = {"status": "ignored", "event_type": event_type}

    if event_type in _LEMON_ACTIVATE:
        updated = S.activate_subscription(
            subscription_id=subscription_id,
            checkout_id=str(attrs.get("order_id") or ""),
            provider_subscription_id=str(data.get("id") or ""),
            provider_customer_id=str(attrs.get("customer_id") or ""),
            current_period_end=str(attrs.get("renews_at") or ""),
        )
        result = {"status": "activated" if updated else "unmatched",
                  "event_type": event_type}
    elif event_type in _LEMON_CANCEL:
        updated = S.set_subscription_status(
            subscription_id=subscription_id,
            provider_subscription_id=str(data.get("id") or ""),
            status=S.STATUS_CANCELLED)
        result = {"status": "cancelled" if updated else "unmatched",
                  "event_type": event_type}
    elif event_type in _LEMON_PAST_DUE:
        updated = S.set_subscription_status(
            subscription_id=subscription_id,
            provider_subscription_id=str(data.get("id") or ""),
            status=S.STATUS_PAST_DUE)
        result = {"status": "past_due" if updated else "unmatched",
                  "event_type": event_type}

    S.mark_event_result(PR.LEMON_SQUEEZY, event_id, result["status"])
    return result
