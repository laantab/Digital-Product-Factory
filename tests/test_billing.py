"""Billing: plan catalog, founder seats, webhook verification, and checkout.

Three areas here are the ones that cost real money when they are wrong:

  * **The founder cap.** Selling seat 101 of 100 is a promise broken in
    public. The cap is tested at the boundary, across abandonment, and across
    cancellation.
  * **Webhook trust.** Anything that can flip a subscription to active must be
    proven to come from the provider. Every way a forged webhook could arrive
    is tested to be rejected.
  * **Price agreement.** The catalog and the provider must charge the same
    amount, and a disagreement must stop checkout rather than pick one.

No test here touches the network; provider calls are substituted.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import unittest
from unittest import mock

import database
from services.billing import plans as P
from services.billing import providers as PR
from services.billing import service as SVC
from services.billing import store as S


def _reset_billing_tables() -> None:
    S.init_billing_db()
    conn = database.get_conn()
    try:
        conn.execute("DELETE FROM billing_subscriptions")
        conn.execute("DELETE FROM billing_events")
        conn.execute("DELETE FROM billing_usage")
        conn.commit()
    finally:
        conn.close()


class PlanCatalogTests(unittest.TestCase):
    """Pricing is coherent, and inside the band the owner asked for."""

    def test_every_paid_plan_sits_in_the_requested_price_band(self):
        for plan in P.ALL_PLANS:
            if plan.monthly_cents:
                with self.subTest(plan=plan.id):
                    self.assertGreaterEqual(plan.monthly_cents, 999)
                    self.assertLessEqual(plan.monthly_cents, 3999)

    def test_the_ladder_increases_in_price_and_in_capacity(self):
        ladder = [P.STARTER, P.PRO, P.STUDIO]
        for lower, higher in zip(ladder, ladder[1:]):
            with self.subTest(pair=(lower.id, higher.id)):
                self.assertLess(lower.monthly_cents, higher.monthly_cents)
                self.assertLess(lower.products_per_month, higher.products_per_month)

    def test_annual_really_does_save_at_least_two_months(self):
        # The pricing page advertises "2 months free" on the annual tab. Annual
        # prices are additionally rounded down to a whole dollar, so the
        # guarantee is "at most ten months of the monthly price", not exactly.
        for plan in (P.STARTER, P.PRO, P.STUDIO):
            with self.subTest(plan=plan.id):
                self.assertLessEqual(plan.annual_cents, plan.monthly_cents * 10)
                self.assertGreater(plan.annual_cents, plan.monthly_cents * 9)
                # Whole dollars, so the page never shows "$249.90 per year".
                self.assertEqual(plan.annual_cents % 100, 0)

    def test_exactly_one_plan_is_flagged_most_popular(self):
        highlighted = [p for p in P.ALL_PLANS if p.highlight]
        self.assertEqual([p.id for p in highlighted], ["pro"])

    def test_no_paid_plan_promises_unmetered_generation(self):
        # Unmetered generation on a cheap tier is a margin trap: the heaviest
        # users would pay least and cost most.
        for plan in P.ALL_PLANS:
            with self.subTest(plan=plan.id):
                self.assertGreater(plan.products_per_month, 0)

    def test_founder_plan_undercuts_pro_and_locks_the_price(self):
        # "Everything in Pro, for less than half the Pro price" is printed on
        # the card, so it has to remain true.
        self.assertLess(P.FOUNDER.annual_cents, P.PRO.annual_cents // 2)
        # ...and it must sit above Starter annual, or the two plans read as the
        # same offer and Starter annual has no reason to exist.
        self.assertGreater(P.FOUNDER.annual_cents, P.STARTER.annual_cents)
        self.assertTrue(P.FOUNDER.price_locked_for_life)
        self.assertEqual(P.FOUNDER.limited_seats, 100)
        # Founder entitlements match Pro, so the offer is a discount and not a
        # different, worse product.
        self.assertEqual(
            P.FOUNDER.products_per_month, P.PRO.products_per_month)

    def test_founder_plan_is_annual_only(self):
        self.assertTrue(P.is_period_available(P.FOUNDER, P.ANNUAL))
        self.assertFalse(P.is_period_available(P.FOUNDER, P.MONTHLY))

    def test_prices_render_the_way_a_customer_expects(self):
        self.assertEqual(P.format_price(0), "$0")
        self.assertEqual(P.format_price(999), "$9.99")
        self.assertEqual(P.format_price(2499), "$24.99")
        self.assertEqual(P.format_price(9900), "$99")

    def test_unknown_plan_is_rejected(self):
        with self.assertRaises(ValueError):
            P.get_plan("enterprise")

    def test_a_provider_price_that_disagrees_stops_checkout(self):
        P.verify_provider_price("pro", P.MONTHLY, 2499, "usd")  # agrees
        with self.assertRaises(ValueError):
            P.verify_provider_price("pro", P.MONTHLY, 2999, "usd")
        with self.assertRaises(ValueError):
            P.verify_provider_price("pro", P.MONTHLY, 2499, "gbp")

    def test_catalog_reports_seats_for_the_founder_plan(self):
        payload = P.catalog(founder_seats_remaining=42)
        founder = next(p for p in payload["plans"] if p["id"] == "founder")
        self.assertEqual(founder["seats_remaining"], 42)
        self.assertEqual(founder["seats_total"], 100)
        self.assertFalse(founder["sold_out"])
        sold_out = P.catalog(founder_seats_remaining=0)
        self.assertTrue(
            next(p for p in sold_out["plans"] if p["id"] == "founder")["sold_out"])


class FounderSeatTests(unittest.TestCase):
    """The cohort is exactly 100 people, however checkout behaves."""

    def setUp(self):
        _reset_billing_tables()

    def _reserve(self, ref: str, limit: int = 100):
        return S.reserve_founder_seat(
            account_ref=ref, provider="stripe", billing_period="annual",
            price_cents=9900, currency="usd", limit=limit)

    def test_seats_are_handed_out_in_order(self):
        for expected in (1, 2, 3):
            row = self._reserve(f"acct_{expected}")
            self.assertEqual(row["founder_seat"], expected)

    def test_the_hundred_and_first_buyer_is_refused(self):
        for i in range(100):
            self._reserve(f"acct_{i}")
        self.assertEqual(S.founder_seats_taken(), 100)
        self.assertEqual(S.founder_seats_remaining(100), 0)
        with self.assertRaises(S.SeatsSoldOutError):
            self._reserve("acct_too_late")

    def test_two_buyers_cannot_hold_the_same_seat(self):
        rows = [self._reserve(f"acct_{i}") for i in range(25)]
        seats = [r["founder_seat"] for r in rows]
        self.assertEqual(len(seats), len(set(seats)))

    def test_an_abandoned_checkout_returns_its_seat(self):
        row = self._reserve("acct_ghost")
        self.assertEqual(S.founder_seats_taken(), 1)
        # Simulate the reservation window elapsing.
        conn = database.get_conn()
        try:
            conn.execute(
                "UPDATE billing_subscriptions SET reserved_until = ? WHERE id = ?",
                ("2000-01-01T00:00:00+00:00", row["id"]))
            conn.commit()
        finally:
            conn.close()
        self.assertEqual(S.founder_seats_taken(), 0)
        self.assertEqual(self._reserve("acct_next")["founder_seat"], 1)

    def test_a_confirmed_seat_is_not_expired(self):
        row = self._reserve("acct_paid")
        S.activate_subscription(subscription_id=row["id"],
                                provider_subscription_id="sub_123")
        conn = database.get_conn()
        try:
            fresh = conn.execute(
                "SELECT status, reserved_until, founder_seat FROM billing_subscriptions"
                " WHERE id = ?", (row["id"],)).fetchone()
        finally:
            conn.close()
        self.assertEqual(fresh["status"], S.STATUS_ACTIVE)
        self.assertIsNone(fresh["reserved_until"])
        self.assertEqual(S.founder_seats_taken(), 1)

    def test_cancelling_returns_the_seat_to_the_cohort(self):
        row = self._reserve("acct_leaver")
        S.activate_subscription(subscription_id=row["id"],
                                provider_subscription_id="sub_leaver")
        self.assertEqual(S.founder_seats_taken(), 1)
        S.set_subscription_status(
            provider_subscription_id="sub_leaver", status=S.STATUS_CANCELLED)
        self.assertEqual(S.founder_seats_taken(), 0)

    def test_a_past_due_subscription_keeps_its_seat(self):
        row = self._reserve("acct_late")
        S.activate_subscription(subscription_id=row["id"],
                                provider_subscription_id="sub_late")
        S.set_subscription_status(
            provider_subscription_id="sub_late", status=S.STATUS_PAST_DUE)
        self.assertEqual(S.founder_seats_taken(), 1)


class StripeWebhookTests(unittest.TestCase):
    """Only Stripe can tell the Factory that somebody paid."""

    SECRET = "whsec_test_secret"

    def _sign(self, payload: bytes, timestamp: int | None = None,
              secret: str | None = None) -> str:
        ts = int(time.time()) if timestamp is None else timestamp
        signed = f"{ts}.".encode() + payload
        mac = hmac.new((secret or self.SECRET).encode(), signed,
                       hashlib.sha256).hexdigest()
        return f"t={ts},v1={mac}"

    def test_a_correctly_signed_event_is_accepted(self):
        payload = json.dumps({"id": "evt_1", "type": "ping"}).encode()
        event = PR.verify_stripe_webhook(
            payload, self._sign(payload), secret=self.SECRET)
        self.assertEqual(event["id"], "evt_1")

    def test_a_tampered_body_is_rejected(self):
        payload = json.dumps({"id": "evt_1", "type": "ping"}).encode()
        header = self._sign(payload)
        forged = json.dumps({"id": "evt_1", "type": "paid"}).encode()
        with self.assertRaises(PR.WebhookVerificationError):
            PR.verify_stripe_webhook(forged, header, secret=self.SECRET)

    def test_a_signature_from_the_wrong_secret_is_rejected(self):
        payload = b'{"id":"evt_1"}'
        header = self._sign(payload, secret="whsec_attacker")
        with self.assertRaises(PR.WebhookVerificationError):
            PR.verify_stripe_webhook(payload, header, secret=self.SECRET)

    def test_a_replayed_old_signature_is_rejected(self):
        payload = b'{"id":"evt_1"}'
        header = self._sign(payload, timestamp=int(time.time()) - 4000)
        with self.assertRaises(PR.WebhookVerificationError):
            PR.verify_stripe_webhook(payload, header, secret=self.SECRET)

    def test_a_missing_or_malformed_header_is_rejected(self):
        payload = b'{"id":"evt_1"}'
        for header in ("", "garbage", "t=123", "v1=abc"):
            with self.subTest(header=header):
                with self.assertRaises(PR.WebhookVerificationError):
                    PR.verify_stripe_webhook(payload, header, secret=self.SECRET)


class LemonWebhookTests(unittest.TestCase):
    SECRET = "ls_test_secret"

    def test_a_correctly_signed_event_is_accepted(self):
        payload = json.dumps({"meta": {"event_name": "ping"}}).encode()
        sig = hmac.new(self.SECRET.encode(), payload, hashlib.sha256).hexdigest()
        event = PR.verify_lemon_webhook(payload, sig, secret=self.SECRET)
        self.assertEqual(event["meta"]["event_name"], "ping")

    def test_a_forged_signature_is_rejected(self):
        payload = b'{"meta":{"event_name":"subscription_created"}}'
        with self.assertRaises(PR.WebhookVerificationError):
            PR.verify_lemon_webhook(payload, "0" * 64, secret=self.SECRET)

    def test_a_missing_signature_is_rejected(self):
        with self.assertRaises(PR.WebhookVerificationError):
            PR.verify_lemon_webhook(b"{}", "", secret=self.SECRET)


class WebhookHandlingTests(unittest.TestCase):
    """Providers deliver more than once; that must not double-count anything."""

    def setUp(self):
        _reset_billing_tables()

    def test_a_replayed_stripe_event_changes_nothing(self):
        row = S.create_pending_subscription(
            account_ref="acct_a", plan_id="pro", billing_period="monthly",
            provider="stripe", price_cents=2499, currency="usd",
            checkout_id="cs_1")
        event = {
            "id": "evt_dup", "type": "checkout.session.completed",
            "data": {"object": {"id": "cs_1", "subscription": "sub_1",
                                "customer": "cus_1"}},
        }
        first = SVC.handle_stripe_event(event)
        second = SVC.handle_stripe_event(event)
        self.assertEqual(first["status"], "activated")
        self.assertEqual(second["status"], "duplicate")
        self.assertEqual(
            S.get_subscription(row["id"])["status"], S.STATUS_ACTIVE)

    def test_a_replayed_founder_activation_does_not_take_a_second_seat(self):
        S.reserve_founder_seat(
            account_ref="acct_f", provider="stripe", billing_period="annual",
            price_cents=9900, currency="usd", limit=100, checkout_id="cs_f")
        event = {
            "id": "evt_f", "type": "checkout.session.completed",
            "data": {"object": {"id": "cs_f", "subscription": "sub_f",
                                "customer": "cus_f"}},
        }
        SVC.handle_stripe_event(event)
        SVC.handle_stripe_event(event)
        self.assertEqual(S.founder_seats_taken(), 1)

    def test_stripe_cancellation_marks_the_subscription_cancelled(self):
        S.create_pending_subscription(
            account_ref="acct_b", plan_id="pro", billing_period="monthly",
            provider="stripe", price_cents=2499, currency="usd",
            checkout_id="cs_2")
        SVC.handle_stripe_event({
            "id": "evt_2", "type": "checkout.session.completed",
            "data": {"object": {"id": "cs_2", "subscription": "sub_2"}}})
        SVC.handle_stripe_event({
            "id": "evt_3", "type": "customer.subscription.deleted",
            "data": {"object": {"id": "sub_2"}}})
        self.assertIsNone(S.get_active_subscription("acct_b"))

    def test_a_failed_payment_marks_the_subscription_past_due(self):
        S.create_pending_subscription(
            account_ref="acct_c", plan_id="starter", billing_period="monthly",
            provider="stripe", price_cents=999, currency="usd",
            checkout_id="cs_3")
        SVC.handle_stripe_event({
            "id": "evt_4", "type": "checkout.session.completed",
            "data": {"object": {"id": "cs_3", "subscription": "sub_3"}}})
        SVC.handle_stripe_event({
            "id": "evt_5", "type": "invoice.payment_failed",
            "data": {"object": {"subscription": "sub_3"}}})
        self.assertEqual(
            S.get_active_subscription("acct_c")["status"], S.STATUS_PAST_DUE)

    def test_a_replayed_lemon_event_changes_nothing(self):
        row = S.create_pending_subscription(
            account_ref="acct_d", plan_id="pro", billing_period="annual",
            provider="lemon_squeezy", price_cents=24900, currency="usd")
        event = {
            "meta": {"event_name": "subscription_created",
                     "webhook_id": "wh_1",
                     "custom_data": {"subscription_row": str(row["id"])}},
            "data": {"id": "ls_sub_1", "attributes": {"order_id": "ord_1"}},
        }
        self.assertEqual(SVC.handle_lemon_event(event)["status"], "activated")
        self.assertEqual(SVC.handle_lemon_event(event)["status"], "duplicate")

    def test_an_event_for_an_unknown_subscription_is_reported_unmatched(self):
        result = SVC.handle_stripe_event({
            "id": "evt_ghost", "type": "checkout.session.completed",
            "data": {"object": {"id": "cs_nope", "subscription": "sub_nope"}}})
        self.assertEqual(result["status"], "unmatched")


class CheckoutTests(unittest.TestCase):
    def setUp(self):
        _reset_billing_tables()

    def _configured_env(self, **extra):
        env = {
            "STRIPE_SECRET_KEY": "sk_test_x",
            "STRIPE_WEBHOOK_SECRET": "whsec_x",
            "STRIPE_PRICE_PRO_MONTHLY": "price_pro_m",
            "STRIPE_PRICE_FOUNDER_ANNUAL": "price_founder_a",
        }
        env.update(extra)
        return mock.patch.dict(os.environ, env, clear=False)

    def test_checkout_is_refused_when_no_provider_is_configured(self):
        with mock.patch.dict(os.environ, {
            "STRIPE_SECRET_KEY": "", "STRIPE_WEBHOOK_SECRET": "",
            "LEMONSQUEEZY_API_KEY": "", "LEMONSQUEEZY_STORE_ID": "",
            "LEMONSQUEEZY_WEBHOOK_SECRET": "",
        }, clear=False):
            with self.assertRaises(SVC.CheckoutError) as ctx:
                SVC.start_checkout(plan_id="pro", billing_period="monthly",
                                   provider="stripe", account_ref="acct_x")
            self.assertIn("not configured", str(ctx.exception))

    def test_the_free_plan_never_reaches_checkout(self):
        with self._configured_env():
            with self.assertRaises(SVC.CheckoutError):
                SVC.start_checkout(plan_id="free", billing_period="monthly",
                                   provider="stripe", account_ref="acct_x")

    def test_a_monthly_founder_seat_is_refused(self):
        with self._configured_env():
            with self.assertRaises(SVC.CheckoutError):
                SVC.start_checkout(plan_id="founder", billing_period="monthly",
                                   provider="stripe", account_ref="acct_x")

    def test_an_unknown_provider_is_refused(self):
        with self.assertRaises(SVC.CheckoutError):
            SVC.start_checkout(plan_id="pro", billing_period="monthly",
                               provider="paypal", account_ref="acct_x")

    def test_a_successful_checkout_returns_a_provider_link(self):
        with self._configured_env(), \
             mock.patch.object(PR, "stripe_price",
                               return_value={"unit_amount": 2499, "currency": "usd"}), \
             mock.patch.object(PR, "stripe_create_checkout",
                               return_value={"id": "cs_live", "url": "https://pay.example/cs_live"}):
            result = SVC.start_checkout(
                plan_id="pro", billing_period="monthly", provider="stripe",
                account_ref="acct_ok")
        self.assertEqual(result["checkout_url"], "https://pay.example/cs_live")
        self.assertEqual(result["price_display"], "$24.99")

    def test_a_price_that_disagrees_with_the_catalog_stops_checkout(self):
        with self._configured_env(), \
             mock.patch.object(PR, "stripe_price",
                               return_value={"unit_amount": 4900, "currency": "usd"}), \
             mock.patch.object(PR, "stripe_create_checkout") as created:
            with self.assertRaises(ValueError):
                SVC.start_checkout(plan_id="pro", billing_period="monthly",
                                   provider="stripe", account_ref="acct_bad")
            created.assert_not_called()

    def test_a_founder_seat_is_claimed_before_the_provider_is_called(self):
        with self._configured_env(), \
             mock.patch.object(PR, "stripe_price",
                               return_value={"unit_amount": P.FOUNDER.annual_cents, "currency": "usd"}), \
             mock.patch.object(PR, "stripe_create_checkout",
                               return_value={"id": "cs_f", "url": "https://pay.example/f"}):
            result = SVC.start_checkout(
                plan_id="founder", billing_period="annual", provider="stripe",
                account_ref="acct_founder")
        self.assertEqual(result["founder_seat"], 1)
        self.assertEqual(result["seats_remaining"], 99)

    def test_a_failed_provider_call_gives_the_founder_seat_back(self):
        with self._configured_env(), \
             mock.patch.object(PR, "stripe_price",
                               return_value={"unit_amount": P.FOUNDER.annual_cents, "currency": "usd"}), \
             mock.patch.object(PR, "stripe_create_checkout",
                               side_effect=PR.BillingProviderError("card network down")):
            with self.assertRaises(PR.BillingProviderError):
                SVC.start_checkout(plan_id="founder", billing_period="annual",
                                   provider="stripe", account_ref="acct_fail")
        self.assertEqual(S.founder_seats_taken(), 0)

    def test_checkout_is_refused_once_the_cohort_is_full(self):
        for i in range(100):
            S.reserve_founder_seat(
                account_ref=f"acct_{i}", provider="stripe",
                billing_period="annual", price_cents=9900, currency="usd",
                limit=100)
        with self._configured_env():
            with self.assertRaises(SVC.CheckoutError) as ctx:
                SVC.start_checkout(plan_id="founder", billing_period="annual",
                                   provider="stripe", account_ref="acct_late")
        self.assertIn("fully subscribed", str(ctx.exception).lower())


class SecretHygieneTests(unittest.TestCase):
    def test_provider_status_never_includes_a_key(self):
        with mock.patch.dict(os.environ, {
            "STRIPE_SECRET_KEY": "sk_live_SUPERSECRET",
            "STRIPE_WEBHOOK_SECRET": "whsec_SUPERSECRET",
        }, clear=False):
            report = json.dumps(PR.status_report())
        self.assertNotIn("SUPERSECRET", report)
        self.assertNotIn("sk_live", report)

    def test_status_reports_live_versus_test_mode(self):
        with mock.patch.dict(os.environ, {
            "STRIPE_SECRET_KEY": "sk_test_abc",
            "STRIPE_WEBHOOK_SECRET": "whsec_abc",
        }, clear=False):
            self.assertEqual(PR.stripe_config().mode, "test")
        with mock.patch.dict(os.environ, {
            "STRIPE_SECRET_KEY": "sk_live_abc",
            "STRIPE_WEBHOOK_SECRET": "whsec_abc",
        }, clear=False):
            self.assertEqual(PR.stripe_config().mode, "live")

    def test_customer_payload_never_exposes_provider_ids(self):
        _reset_billing_tables()
        row = S.create_pending_subscription(
            account_ref="acct_p", plan_id="pro", billing_period="monthly",
            provider="stripe", price_cents=2499, currency="usd",
            checkout_id="cs_secret")
        S.activate_subscription(subscription_id=row["id"],
                                provider_subscription_id="sub_secret",
                                provider_customer_id="cus_secret")
        payload = json.dumps(
            SVC.subscription_payload(S.get_active_subscription("acct_p")))
        for leak in ("sub_secret", "cus_secret", "cs_secret"):
            self.assertNotIn(leak, payload)


class BillingRouteTests(unittest.TestCase):
    def setUp(self):
        _reset_billing_tables()
        from app import app as flask_app

        flask_app.config["TESTING"] = True
        self.client = flask_app.test_client()

    def test_plans_endpoint_returns_the_catalog_and_seat_count(self):
        res = self.client.get("/billing/plans")
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        ids = [p["id"] for p in body["plans"]]
        for expected in ("free", "starter", "pro", "studio", "founder"):
            self.assertIn(expected, ids)
        founder = next(p for p in body["plans"] if p["id"] == "founder")
        self.assertEqual(founder["seats_remaining"], 100)

    def test_plans_endpoint_never_returns_a_key(self):
        with mock.patch.dict(os.environ, {
            "STRIPE_SECRET_KEY": "sk_live_LEAKME",
            "STRIPE_WEBHOOK_SECRET": "whsec_LEAKME",
        }, clear=False):
            body = self.client.get("/billing/plans").get_data(as_text=True)
        self.assertNotIn("LEAKME", body)

    def test_account_endpoint_mints_an_opaque_reference(self):
        ref = self.client.post("/billing/account").get_json()["account_ref"]
        self.assertTrue(ref.startswith("acct_"))
        self.assertGreater(len(ref), 10)

    def test_an_unsigned_stripe_webhook_is_rejected(self):
        with mock.patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": "whsec_x"},
                             clear=False):
            res = self.client.post(
                "/billing/webhook/stripe",
                data=json.dumps({"id": "evt_forged",
                                 "type": "checkout.session.completed"}),
                content_type="application/json")
        self.assertEqual(res.status_code, 400)

    def test_an_unsigned_lemon_webhook_is_rejected(self):
        with mock.patch.dict(os.environ,
                             {"LEMONSQUEEZY_WEBHOOK_SECRET": "ls_x"}, clear=False):
            res = self.client.post(
                "/billing/webhook/lemonsqueezy",
                data=json.dumps({"meta": {"event_name": "subscription_created"}}),
                content_type="application/json")
        self.assertEqual(res.status_code, 400)

    def test_a_forged_webhook_cannot_activate_a_subscription(self):
        row = S.create_pending_subscription(
            account_ref="acct_victim", plan_id="pro", billing_period="monthly",
            provider="stripe", price_cents=2499, currency="usd",
            checkout_id="cs_victim")
        with mock.patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": "whsec_real"},
                             clear=False):
            self.client.post(
                "/billing/webhook/stripe",
                data=json.dumps({
                    "id": "evt_forged", "type": "checkout.session.completed",
                    "data": {"object": {"id": "cs_victim"}}}),
                headers={"Stripe-Signature": "t=1,v1=deadbeef"},
                content_type="application/json")
        self.assertEqual(
            S.get_subscription(row["id"])["status"], S.STATUS_RESERVED)

    def test_subscription_endpoint_requires_an_account_reference(self):
        self.assertEqual(self.client.get("/billing/subscription").status_code, 400)

    def test_subscription_endpoint_reports_free_for_a_new_account(self):
        body = self.client.get(
            "/billing/subscription?account_ref=acct_new").get_json()
        self.assertEqual(body["plan_id"], "free")
        self.assertEqual(body["usage"]["products_allowed"], 3)

    def test_checkout_endpoint_reports_a_clean_error_when_unconfigured(self):
        with mock.patch.dict(os.environ, {
            "STRIPE_SECRET_KEY": "", "STRIPE_WEBHOOK_SECRET": "",
        }, clear=False):
            res = self.client.post(
                "/billing/checkout",
                data=json.dumps({"plan_id": "pro", "billing_period": "monthly",
                                 "provider": "stripe",
                                 "account_ref": "acct_z"}),
                content_type="application/json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("not configured", res.get_json()["error"])


class UsageMeteringTests(unittest.TestCase):
    def setUp(self):
        _reset_billing_tables()

    def test_usage_counts_against_the_plan_allowance(self):
        usage = SVC.usage_payload("acct_meter")
        self.assertEqual(usage["products_allowed"], 3)   # free plan
        self.assertEqual(usage["products_used"], 0)
        self.assertFalse(usage["over_limit"])
        for _ in range(3):
            S.record_usage("acct_meter", "faith_planner")
        usage = SVC.usage_payload("acct_meter")
        self.assertEqual(usage["products_used"], 3)
        self.assertEqual(usage["products_remaining"], 0)
        self.assertTrue(usage["over_limit"])

    def test_a_paid_plan_raises_the_allowance(self):
        row = S.create_pending_subscription(
            account_ref="acct_paid", plan_id="pro", billing_period="monthly",
            provider="stripe", price_cents=2499, currency="usd")
        S.activate_subscription(subscription_id=row["id"],
                                provider_subscription_id="sub_paid")
        self.assertEqual(
            SVC.usage_payload("acct_paid")["products_allowed"], 50)


if __name__ == "__main__":
    unittest.main()
