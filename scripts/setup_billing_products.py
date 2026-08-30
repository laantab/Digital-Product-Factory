"""Create the Factory's products and prices in Stripe, from the plan catalog.

Run this yourself — it writes to your Stripe account, so it is never invoked
automatically by the app or by the test suite.

    # See exactly what would be created, without touching the account:
    .venv/Scripts/python.exe scripts/setup_billing_products.py

    # Create everything in TEST mode (needs STRIPE_SECRET_KEY=sk_test_...):
    .venv/Scripts/python.exe scripts/setup_billing_products.py --apply

    # Create everything in LIVE mode (needs sk_live_... and --live as well):
    .venv/Scripts/python.exe scripts/setup_billing_products.py --apply --live

Prices come from services/billing/plans.py and are created there exactly as
written, so the amount Stripe charges cannot drift from the amount the pricing
page shows. Re-running is safe: an existing product with the same lookup key is
reused rather than duplicated.

Lemon Squeezy has no API for creating products, so those are made by hand in
its dashboard; this script prints the amounts to enter.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), ".env"))
except Exception:  # noqa: BLE001
    pass

from services.billing import plans as P  # noqa: E402
from services.billing import providers as PR  # noqa: E402

INTERVALS = {P.MONTHLY: "month", P.ANNUAL: "year"}


def lookup_key(plan_id: str, period: str) -> str:
    return f"factory_{plan_id}_{period}"


def plan_rows() -> list[tuple[P.Plan, str, int]]:
    rows = []
    for plan in sorted(P.ALL_PLANS, key=lambda p: p.order):
        for period in P.BILLING_PERIODS:
            if P.is_period_available(plan, period):
                rows.append((plan, period, plan.price_cents(period)))
    return rows


def show_plan(rows) -> None:
    print("\nPlans to create in Stripe")
    print("-" * 66)
    for plan, period, cents in rows:
        seats = f"  [limited to {plan.limited_seats} seats]" if plan.limited_seats else ""
        print(f"  {plan.name:<16} {period:<8} {P.format_price(cents):>9} "
              f"/ {INTERVALS[period]}{seats}")
    print("-" * 66)
    print("\nLemon Squeezy: create these by hand in your store dashboard, as")
    print("subscription products with the same amounts and intervals, then put")
    print("each variant id in .env as LEMONSQUEEZY_VARIANT_<PLAN>_<PERIOD>.\n")


def find_price(key: str) -> dict | None:
    body = PR._stripe_request(
        "GET", f"/prices?lookup_keys[]={key}&limit=1&active=true")
    data = body.get("data") or []
    return data[0] if data else None


def create_product_and_price(plan: P.Plan, period: str, cents: int) -> str:
    key = lookup_key(plan.id, period)
    existing = find_price(key)
    if existing:
        if int(existing.get("unit_amount") or 0) != cents:
            print(f"  ! {key} exists at "
                  f"{P.format_price(int(existing.get('unit_amount') or 0))} but the "
                  f"catalog says {P.format_price(cents)}.")
            print("    Archive the old price in Stripe and re-run; this script "
                  "will not silently change a live price.")
            return str(existing["id"])
        print(f"  = {key} already exists -> {existing['id']}")
        return str(existing["id"])

    product = PR._stripe_request("POST", "/products", {
        "name": f"Digital Product Factory — {plan.name}",
        "description": plan.tagline,
        "metadata[plan_id]": plan.id,
    })
    price = PR._stripe_request("POST", "/prices", {
        "product": product["id"],
        "unit_amount": cents,
        "currency": P.CURRENCY,
        "recurring[interval]": INTERVALS[period],
        "lookup_key": key,
        "metadata[plan_id]": plan.id,
        "metadata[billing_period]": period,
    })
    print(f"  + {key} -> {price['id']}  ({P.format_price(cents)}/{INTERVALS[period]})")
    return str(price["id"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="actually create the products and prices")
    parser.add_argument("--live", action="store_true",
                        help="permit running against a live (sk_live_) key")
    args = parser.parse_args()

    rows = plan_rows()
    show_plan(rows)

    if not args.apply:
        print("Dry run. Nothing was created. Add --apply to write to Stripe.\n")
        return 0

    cfg = PR.stripe_config()
    if not os.environ.get("STRIPE_SECRET_KEY"):
        print("STRIPE_SECRET_KEY is not set in .env. Nothing to do.")
        return 1
    if cfg.mode == "live" and not args.live:
        print("Refusing to write to a LIVE Stripe account without --live.")
        print("Test everything with an sk_test_ key first.")
        return 1
    if cfg.mode == "unset":
        print("STRIPE_SECRET_KEY does not look like a Stripe key.")
        return 1

    print(f"Writing to Stripe in {cfg.mode.upper()} mode.\n")
    env_lines: list[str] = []
    for plan, period, cents in rows:
        try:
            price_id = create_product_and_price(plan, period, cents)
        except PR.BillingProviderError as exc:
            print(f"  x {plan.id}/{period}: {exc}")
            return 1
        env_lines.append(
            f"{PR.price_env_name(PR.STRIPE, plan.id, period)}={price_id}")

    print("\nPaste these into .env, then restart the app:\n")
    print("\n".join(env_lines))
    print("\nNext: add the webhook endpoint")
    print(f"  {os.environ.get('FACTORY_PUBLIC_URL', 'http://127.0.0.1:5000')}"
          "/billing/webhook/stripe")
    print("  events: checkout.session.completed, customer.subscription.updated,")
    print("          customer.subscription.deleted, invoice.payment_failed")
    print("and put its signing secret in STRIPE_WEBHOOK_SECRET.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
