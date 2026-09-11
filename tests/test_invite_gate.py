"""Invite-code gate for the private beta (2026-09-11).

WHY THIS EXISTS
---------------
The public host (digitalproductfactorypro.com) served every one of the
Factory's ~93 routes to anyone who found the domain -- including the routes
that spend OpenAI / Tavily / Pexels credit and the /admin/* routes. Until
real accounts exist, one shared invite code (FACTORY_INVITE_CODE, set on the
HOST, never in the local .env) guards the whole app.

THE CONTRACT
------------
- Gate off (no code configured): every route behaves exactly as before.
- Gate on: a request is admitted by the `factory_invite` cookie, the
  `X-Factory-Invite` header, or once via `?invite=CODE` on a GET (which sets
  the cookie and redirects). Browsers without a code see a one-field invite
  page (401); API calls get `401 {"error": "Invite code required."}`.
- Exempt: /static/*, /billing/webhook/* (signature-verified, and Lemon
  Squeezy / Stripe cannot send a cookie), and /invite itself.
- A wrong code is refused everywhere and gets no hint.

These tests switch the gate on by patching `app._invite_code_required`
rather than the environment, so a stray value in a local .env can never gate
the rest of the suite (under FACTORY_TEST_MODE the reader always returns "").

No external/paid API call is made by any test in this file.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("FACTORY_TEST_MODE", "1")

import app as app_module  # noqa: E402
from app import app  # noqa: E402

CODE = "beta-orchard-2026"
REFUSED = "Invite code required."


class _GateOn:
    """Turn the gate on with a known code for the duration of a test."""

    def __enter__(self):
        self._orig = app_module._invite_code_required
        app_module._invite_code_required = lambda: CODE
        return self

    def __exit__(self, *exc):
        app_module._invite_code_required = self._orig
        return False


class GateOffTests(unittest.TestCase):
    """With no code configured, nothing about the Factory changes."""

    def test_home_page_loads_without_any_code(self):
        r = app.test_client().get("/", headers={"Accept": "text/html"})
        self.assertEqual(r.status_code, 200)

    def test_api_routes_are_open(self):
        r = app.test_client().get("/projects")
        self.assertEqual(r.status_code, 200)

    def test_invite_page_just_redirects_home(self):
        r = app.test_client().get("/invite")
        self.assertEqual(r.status_code, 302)


class GateOnRefusalTests(unittest.TestCase):
    def test_browser_without_code_sees_the_invite_page(self):
        with _GateOn():
            r = app.test_client().get("/", headers={"Accept": "text/html"})
        self.assertEqual(r.status_code, 401)
        self.assertIn(b"Invite code", r.data)
        self.assertIn(b'action="/invite"', r.data)

    def test_api_call_without_code_gets_a_json_401(self):
        with _GateOn():
            r = app.test_client().get("/projects")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.get_json()["error"], REFUSED)

    def test_generation_is_refused_without_code(self):
        with _GateOn():
            r = app.test_client().post(
                "/generate-product", json={"product_type": "word_search", "fields": {}}
            )
        self.assertEqual(r.status_code, 401)

    def test_admin_routes_are_gated(self):
        with _GateOn():
            r = app.test_client().post("/admin/backup-db")
        self.assertEqual(r.status_code, 401)

    def test_wrong_code_is_refused_everywhere(self):
        with _GateOn():
            c = app.test_client()
            self.assertEqual(c.get("/projects", headers={"X-Factory-Invite": "nope"}).status_code, 401)
            c.set_cookie("factory_invite", "nope")
            self.assertEqual(c.get("/projects").status_code, 401)
            self.assertEqual(c.get("/?invite=nope").status_code, 401)
            r = c.post("/invite", data={"code": "nope"})
            self.assertEqual(r.status_code, 401)
            self.assertIn(b"didn't work", r.data)
            self.assertNotIn(CODE.encode(), r.data)


class GateOnAdmissionTests(unittest.TestCase):
    def test_header_admits(self):
        with _GateOn():
            r = app.test_client().get("/projects", headers={"X-Factory-Invite": CODE})
        self.assertEqual(r.status_code, 200)

    def test_cookie_admits(self):
        with _GateOn():
            c = app.test_client()
            c.set_cookie("factory_invite", CODE)
            r = c.get("/projects")
        self.assertEqual(r.status_code, 200)

    def test_query_code_sets_the_cookie_and_redirects(self):
        with _GateOn():
            c = app.test_client()
            r = c.get("/?invite=" + CODE)
            self.assertEqual(r.status_code, 302)
            self.assertIn("factory_invite=", r.headers.get("Set-Cookie", ""))
            # The cookie now carries the session: same client, no code in the URL.
            self.assertEqual(c.get("/", headers={"Accept": "text/html"}).status_code, 200)
            self.assertEqual(c.get("/projects").status_code, 200)

    def test_invite_form_with_the_right_code_admits(self):
        with _GateOn():
            c = app.test_client()
            self.assertEqual(c.get("/invite").status_code, 200)
            r = c.post("/invite", data={"code": CODE})
            self.assertEqual(r.status_code, 302)
            self.assertIn("factory_invite=", r.headers.get("Set-Cookie", ""))
            self.assertEqual(c.get("/projects").status_code, 200)


class GateOnExemptionTests(unittest.TestCase):
    def test_static_files_stay_reachable(self):
        with _GateOn():
            r = app.test_client().get("/static/js/app.js")
        self.assertEqual(r.status_code, 200)

    def test_billing_webhooks_are_never_gated(self):
        # They are signature-verified and the providers cannot send a cookie.
        # Whatever they return to an unsigned body, it must not be the gate.
        with _GateOn():
            c = app.test_client()
            for path in ("/billing/webhook/lemonsqueezy", "/billing/webhook/stripe"):
                with self.subTest(path=path):
                    r = c.post(path, data=b"{}", headers={"Content-Type": "application/json"})
                    self.assertNotEqual((r.get_json(silent=True) or {}).get("error"), REFUSED)


if __name__ == "__main__":
    unittest.main()
