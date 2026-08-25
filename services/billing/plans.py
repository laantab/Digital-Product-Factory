"""The Factory's plan catalog — one source of truth for pricing.

Prices live here, in code, rather than being read back from Stripe or Lemon
Squeezy. The provider is asked to charge an amount this file already decided;
if the two ever disagree, `verify_provider_price` says so loudly instead of
letting a mispriced checkout through.

Why these numbers
-----------------
Every finished product costs the Factory real money to make (model calls, and
sometimes a stock-photo lookup), so an unmetered plan at the bottom of the
ladder is a margin trap: the heaviest users would pay the least and cost the
most. The paid tiers are therefore metered by finished products per month, and
"effectively unlimited" only appears at the top, where the price can absorb it.

The ladder is good / better / best with the middle tier as the intended
default: Pro is the one flagged Most Popular, and Studio exists partly to make
Pro read as the sensible choice.

Amounts are integer cents. Never use floats for money.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from typing import Any

MONTHLY = "monthly"
ANNUAL = "annual"
BILLING_PERIODS = (MONTHLY, ANNUAL)

CURRENCY = os.environ.get("FACTORY_BILLING_CURRENCY", "usd").lower()

# The founding cohort. A hard cap, enforced in the database rather than by
# hiding the button — see `services.billing.store.reserve_founder_seat`.
FOUNDER_SEAT_LIMIT = int(os.environ.get("FACTORY_FOUNDER_SEATS", "100"))


@dataclass(frozen=True)
class Plan:
    id: str
    name: str
    tagline: str
    monthly_cents: int
    annual_cents: int
    products_per_month: int          # -1 means no metered cap
    features: tuple[str, ...] = ()
    highlight: bool = False          # "Most Popular" badge
    limited_seats: int = 0           # 0 means unlimited availability
    price_locked_for_life: bool = False
    order: int = 0
    note: str = ""

    def price_cents(self, period: str) -> int:
        return self.annual_cents if period == ANNUAL else self.monthly_cents

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["features"] = list(self.features)
        d["monthly_display"] = format_price(self.monthly_cents)
        d["annual_display"] = format_price(self.annual_cents)
        d["annual_monthly_equivalent"] = (
            format_price(round(self.annual_cents / 12)) if self.annual_cents else ""
        )
        d["annual_saving_display"] = (
            format_price(self.monthly_cents * 12 - self.annual_cents)
            if self.monthly_cents and self.annual_cents else ""
        )
        d["metered"] = self.products_per_month >= 0
        return d


def format_price(cents: int) -> str:
    if cents <= 0:
        return "$0"
    whole, part = divmod(int(cents), 100)
    return f"${whole}" if part == 0 else f"${whole}.{part:02d}"


FREE = Plan(
    id="free",
    name="Free",
    tagline="Try the Factory on three real products",
    monthly_cents=0,
    annual_cents=0,
    products_per_month=3,
    order=0,
    features=(
        "3 finished products per month",
        "Ebooks, coloring books, puzzles, and planners",
        "Factory Market Advantage research (3 searches per month)",
        "PDF download, no watermark",
        "Editor-in-Chief quality review on every export",
    ),
)

STARTER = Plan(
    id="starter",
    name="Starter",
    tagline="For the first products you intend to sell",
    monthly_cents=999,
    annual_cents=9900,
    products_per_month=10,
    order=1,
    features=(
        "10 finished products per month",
        "Every product type, including Faith and Budget planners",
        "PDF and ZIP export packages",
        "Publishing Studio templates",
        "KDP and Etsy listing preflight",
        "Email support",
    ),
)

PRO = Plan(
    id="pro",
    name="Pro",
    tagline="For a real catalog and a real launch",
    monthly_cents=2499,
    annual_cents=24900,
    products_per_month=50,
    highlight=True,
    order=2,
    features=(
        "50 finished products per month",
        "Everything in Starter",
        "Unlimited Factory Market Advantage research",
        "Launch Package: landing page, freebie, ads, email sequence",
        "Ad and promotion package generator",
        "Priority generation queue",
        "Priority support",
    ),
)

STUDIO = Plan(
    id="studio",
    name="Studio",
    tagline="For selling under your own brand, at volume",
    monthly_cents=3999,
    annual_cents=39900,
    products_per_month=200,
    order=3,
    note="200 products a month is a fair-use ceiling, not a hard stop — talk to "
         "us before you hit it.",
    features=(
        "200 finished products per month",
        "Everything in Pro",
        "White-label exports with your own brand on every page",
        "Commercial resale licence",
        "Bulk export and batch generation",
        "Named support contact",
    ),
)

FOUNDER = Plan(
    id="founder",
    name="Founder's Plan",
    tagline="For the first 100 people who back the Factory",
    monthly_cents=0,                  # annual only, on purpose
    # $119/yr — just under half of Pro's $249, and deliberately *above*
    # Starter's $99. Pricing it at $99 made the two identical on the page,
    # which both flattened the founder offer and left Starter annual with no
    # reason to exist while seats remained.
    annual_cents=11900,
    products_per_month=50,            # Pro-level entitlements
    limited_seats=FOUNDER_SEAT_LIMIT,
    price_locked_for_life=True,
    order=4,
    note="Annual only. Your price never rises for as long as the subscription "
         "stays active — including through every future price increase.",
    features=(
        "Everything in Pro, for less than half the Pro price",
        "50 finished products per month",
        "Price locked for life — renewals never increase",
        "Founding member badge on your account",
        "Direct line to the roadmap: founders vote on what gets built next",
        "First access to every new product type",
    ),
)

ALL_PLANS: tuple[Plan, ...] = (FREE, STARTER, PRO, STUDIO, FOUNDER)
PLANS_BY_ID = {p.id: p for p in ALL_PLANS}
PAID_PLAN_IDS = tuple(p.id for p in ALL_PLANS if p.monthly_cents or p.annual_cents)
DEFAULT_PLAN_ID = FREE.id


def get_plan(plan_id: str) -> Plan:
    plan = PLANS_BY_ID.get(str(plan_id or "").strip().lower())
    if plan is None:
        raise ValueError(f"Unknown plan: {plan_id!r}")
    return plan


def is_period_available(plan: Plan, period: str) -> bool:
    """The Founder's Plan is annual only; a monthly founder seat would let
    someone hold a lifetime-locked price for one month's commitment."""
    if period not in BILLING_PERIODS:
        return False
    return plan.price_cents(period) > 0


def verify_provider_price(plan_id: str, period: str, provider_cents: int,
                          provider_currency: str = CURRENCY) -> None:
    """Fail loudly when the payment provider is configured to charge something
    this catalog did not authorise. Silent disagreement here means charging a
    customer the wrong amount."""
    plan = get_plan(plan_id)
    expected = plan.price_cents(period)
    if int(provider_cents) != int(expected):
        raise ValueError(
            f"Price mismatch for {plan_id}/{period}: catalog says "
            f"{format_price(expected)}, provider says {format_price(provider_cents)}. "
            "Refusing to start checkout."
        )
    if str(provider_currency or "").lower() != CURRENCY:
        raise ValueError(
            f"Currency mismatch for {plan_id}: expected {CURRENCY!r}, "
            f"provider says {provider_currency!r}."
        )


def entitlements(plan_id: str) -> dict[str, Any]:
    plan = get_plan(plan_id)
    return {
        "plan_id": plan.id,
        "plan_name": plan.name,
        "products_per_month": plan.products_per_month,
        "metered": plan.products_per_month >= 0,
        "white_label": plan.id == STUDIO.id,
        "commercial_licence": plan.id in (STUDIO.id,),
        "unlimited_research": plan.id in (PRO.id, STUDIO.id, FOUNDER.id),
        "launch_package": plan.id in (PRO.id, STUDIO.id, FOUNDER.id),
        "priority_queue": plan.id in (PRO.id, STUDIO.id, FOUNDER.id),
        "founding_member": plan.id == FOUNDER.id,
        "price_locked_for_life": plan.price_locked_for_life,
    }


def catalog(*, founder_seats_remaining: int | None = None) -> dict[str, Any]:
    """The payload the pricing page renders from."""
    plans = []
    for plan in sorted(ALL_PLANS, key=lambda p: p.order):
        row = plan.as_dict()
        row["periods"] = [p for p in BILLING_PERIODS if is_period_available(plan, p)]
        if plan.limited_seats:
            remaining = (
                plan.limited_seats if founder_seats_remaining is None
                else max(0, int(founder_seats_remaining))
            )
            row["seats_total"] = plan.limited_seats
            row["seats_remaining"] = remaining
            row["sold_out"] = remaining <= 0
        plans.append(row)
    return {
        "currency": CURRENCY,
        "plans": plans,
        "default_plan_id": DEFAULT_PLAN_ID,
        "founder_seat_limit": FOUNDER_SEAT_LIMIT,
    }
