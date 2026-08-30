"""Find your Lemon Squeezy store and variant ids, and print the .env lines.

Lemon Squeezy has no API for *creating* products, so those are made by hand in
its dashboard. Hunting for the id of each one afterwards is where mistakes
happen, so this script does that part for you: it reads your store, lists every
subscription variant, matches each one to a plan in the Factory's catalog by
price and interval, and prints the exact lines to paste into .env.

    .venv/Scripts/python.exe scripts/lemonsqueezy_ids.py

Read-only. It never creates, changes, or deletes anything in your account, and
it never prints your API key.
"""
from __future__ import annotations

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

INTERVAL_FOR = {P.MONTHLY: "month", P.ANNUAL: "year"}


def expected_rows() -> list[tuple[P.Plan, str, int]]:
    rows = []
    for plan in sorted(P.ALL_PLANS, key=lambda p: p.order):
        for period in P.BILLING_PERIODS:
            if P.is_period_available(plan, period):
                rows.append((plan, period, plan.price_cents(period)))
    return rows


def show_shopping_list() -> None:
    print("\nCreate these 7 subscription products in your Lemon Squeezy")
    print("dashboard, with TEST MODE switched on.\n")
    print(f"  {'Product name':<42} {'Price':>9}  Billing")
    print("  " + "-" * 66)
    for plan, period, cents in expected_rows():
        name = f"Digital Product Factory - {plan.name} ({period.title()})"
        print(f"  {name:<42} {P.format_price(cents):>9}  every {INTERVAL_FOR[period]}")
    print()


def fetch_store_id() -> str:
    configured = os.environ.get("LEMONSQUEEZY_STORE_ID", "").strip()
    body = PR._lemon_request("GET", "/stores")
    stores = body.get("data") or []
    if not stores:
        print("No stores found on this account.")
        return configured
    if len(stores) == 1:
        sid = str(stores[0]["id"])
        name = (stores[0].get("attributes") or {}).get("name") or "(unnamed)"
        print(f"Store: {name}  ->  LEMONSQUEEZY_STORE_ID={sid}\n")
        return sid
    print("You have more than one store. Pick the id you want:\n")
    for s in stores:
        name = (s.get("attributes") or {}).get("name") or "(unnamed)"
        print(f"  {s['id']}   {name}")
    print()
    return configured


def fetch_variants(store_id: str) -> list[dict]:
    """Every subscription variant in *this* store, flattened to what we need.

    Two things this deliberately does not do:

      * It does not filter on variant status. A single-variant product sits at
        status "pending" in Lemon Squeezy even when its product is published
        and selling; filtering for "published" hides every one of them and
        reports a correctly configured store as empty.
      * It does not read /variants globally. That endpoint spans every store on
        the account, so a second store's products would be matched into this
        one's config. Variants are fetched per product instead, and products
        are already scoped to the store.
    """
    out: list[dict] = []
    products: list[str] = []
    page = 1
    while True:
        body = PR._lemon_request(
            "GET",
            f"/products?filter[store_id]={store_id}"
            f"&page[number]={page}&page[size]=100",
        )
        products.extend(str(p.get("id")) for p in (body.get("data") or []))
        meta_page = (body.get("meta") or {}).get("page") or {}
        if page >= int(meta_page.get("lastPage") or 1):
            break
        page += 1

    for product_id in products:
        body = PR._lemon_request(
            "GET", f"/variants?filter[product_id]={product_id}&page[size]=100")
        for v in (body.get("data") or []):
            attrs = v.get("attributes") or {}
            if not attrs.get("is_subscription"):
                continue
            out.append({
                "id": str(v.get("id")),
                "name": attrs.get("name") or "",
                "price": int(attrs.get("price") or 0),
                "interval": str(attrs.get("interval") or ""),
                "interval_count": int(attrs.get("interval_count") or 1),
                "product_id": product_id,
            })
    return out


def match(variants: list[dict]) -> tuple[list[str], list[str]]:
    """Match each catalog plan to a variant by price + interval."""
    env_lines: list[str] = []
    missing: list[str] = []
    for plan, period, cents in expected_rows():
        want_interval = INTERVAL_FOR[period]
        hits = [
            v for v in variants
            if v["price"] == cents
            and v["interval"] == want_interval
            and v["interval_count"] == 1
        ]
        env_name = PR.price_env_name(PR.LEMON_SQUEEZY, plan.id, period)
        if len(hits) == 1:
            env_lines.append(f"{env_name}={hits[0]['id']}")
        elif not hits:
            missing.append(
                f"  {plan.name} ({period}) at {P.format_price(cents)} "
                f"every {want_interval} - no matching product found"
            )
        else:
            ids = ", ".join(h["id"] for h in hits)
            missing.append(
                f"  {plan.name} ({period}) at {P.format_price(cents)} - "
                f"several products match ({ids}); delete the duplicates, "
                f"or set {env_name} by hand"
            )
    return env_lines, missing


def main() -> int:
    if not os.environ.get("LEMONSQUEEZY_API_KEY", "").strip():
        print("\nLEMONSQUEEZY_API_KEY is not set in .env yet.\n")
        show_shopping_list()
        print("Add your API key to .env first, then run this again.\n")
        return 1

    try:
        store_id = fetch_store_id()
        variants = fetch_variants(store_id)
    except PR.BillingConfigError as exc:
        print(f"\nConfiguration problem: {exc}\n")
        return 1
    except PR.BillingProviderError as exc:
        print(f"\nLemon Squeezy said no: {exc}")
        print("Check that the API key is correct and has not expired.\n")
        return 1

    if not variants:
        print("No subscription products found in this store yet.")
        show_shopping_list()
        print("Create them, then run this again.\n")
        return 1

    print(f"Found {len(variants)} subscription product(s):\n")
    for v in sorted(variants, key=lambda v: v["price"]):
        print(f"  {v['id']:>10}  {P.format_price(v['price']):>9} "
              f"every {v['interval']}   {v['name']}")
    print()

    env_lines, missing = match(variants)

    if env_lines:
        print("Paste these lines into .env (replacing the empty ones):\n")
        if store_id:
            print(f"LEMONSQUEEZY_STORE_ID={store_id}")
        print("\n".join(env_lines))
        print()

    if missing:
        print("Still missing - the price or interval does not match the catalog:\n")
        print("\n".join(missing))
        print("\nPrices must match exactly. See the list above for what to create.\n")
        return 1

    print("All 7 plans matched. After pasting, restart the app and the")
    print("pricing page will switch checkout on.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
