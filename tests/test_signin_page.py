"""Factory 1.8.6: the sign-in page at GET /auth/signin.

The page is static HTML plus a small script that posts JSON to the existing
/auth routes. These tests check that it is served, stays behind the invite
gate, never echoes anything from the request, never puts the secret in a
URL, and that the JSON routes it relies on still refuse plain form posts
(the reason a page on another site cannot sign someone in or up).
Throwaway test values only.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("FACTORY_TEST_MODE", "1")

import app as app_module  # noqa: E402
import database  # noqa: E402
import routes.auth as auth_routes  # noqa: E402

PW = "test-only-pass-123"


class _Base(unittest.TestCase):
    invite = ""

    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(self.path)
        for p in (patch.object(database, "DB_PATH", self.path),
                  patch.object(database, "_use_postgres", return_value=False),
                  patch.object(auth_routes, "_BCRYPT_ROUNDS", 4),
                  patch.object(app_module, "_invite_code_required", return_value=self.invite)):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(lambda: [os.path.exists(x) and os.unlink(x)
                                 for x in (self.path, self.path + "-wal", self.path + "-shm")])
        database.init_db()
        self.client = app_module.app.test_client()


class SignInPageTests(_Base):

    def test_page_is_served_as_html(self):
        r = self.client.get("/auth/signin")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/html", r.headers["Content-Type"])
        html = r.get_data(as_text=True)
        for needed in ('id="login-form"', 'id="register-form"', "/auth/login",
                       "/auth/register", "/auth/logout", "/auth/me"):
            self.assertIn(needed, html)

    def test_page_is_not_cached_or_framed(self):
        r = self.client.get("/auth/signin")
        self.assertEqual(r.headers.get("Cache-Control"), "no-store")
        self.assertEqual(r.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(r.headers.get("Referrer-Policy"), "no-referrer")

    def test_secret_fields_are_password_inputs(self):
        html = self.client.get("/auth/signin").get_data(as_text=True)
        for field in ("login-password", "reg-password", "reg-confirm"):
            self.assertRegex(html, r'<input id="%s"[^>]*type="password"' % field)

    def test_page_never_sends_the_secret_in_a_url_or_as_a_form(self):
        html = self.client.get("/auth/signin").get_data(as_text=True)
        self.assertNotIn("method=\"get\"", html.lower())
        self.assertNotIn("action=", html.lower())
        self.assertIn('"Content-Type": "application/json"', html)
        self.assertNotIn("innerHTML", html)

    def test_page_echoes_nothing_from_the_request(self):
        marker = "<script>alert(1)</script>"
        r = self.client.get("/auth/signin?email=" + marker + "&error=" + marker)
        self.assertNotIn(marker, r.get_data(as_text=True))

    def test_page_is_identical_when_signed_in(self):
        before = self.client.get("/auth/signin").get_data(as_text=True)
        self.client.post("/auth/register", json={"email": "owner@example.com", "password": PW})
        after = self.client.get("/auth/signin").get_data(as_text=True)
        self.assertEqual(before, after)
        self.assertNotIn("owner@example.com", after)


class JsonOnlyTests(_Base):

    def test_plain_form_posts_cannot_register_or_sign_in(self):
        r = self.client.post("/auth/register",
                             data={"email": "owner@example.com", "password": PW})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(database.count_users(), 0)
        self.client.post("/auth/register", json={"email": "owner@example.com", "password": PW})
        c = app_module.app.test_client()
        r = c.post("/auth/login", data={"email": "owner@example.com", "password": PW})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(c.get("/auth/me").status_code, 401)

    def test_page_flow_register_then_sign_in(self):
        r = self.client.post("/auth/register", json={"email": "owner@example.com", "password": PW})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()["user"]["role"], "admin")
        c = app_module.app.test_client()
        self.assertEqual(c.post("/auth/login",
                                json={"email": "owner@example.com", "password": PW}).status_code, 200)
        self.assertEqual(c.get("/auth/me").get_json()["user"]["email"], "owner@example.com")


class InviteGateStillAppliesTests(_Base):
    invite = "test-invite-code"

    def test_page_requires_the_invite_code(self):
        r = self.client.get("/auth/signin")
        self.assertIn(r.status_code, (401, 302))
        self.assertNotIn('id="register-form"', r.get_data(as_text=True))

    def test_page_opens_with_the_invite_code(self):
        r = self.client.get("/auth/signin", headers={"X-Invite-Code": "test-invite-code"})
        if r.status_code != 200:
            r = self.client.get("/auth/signin?invite=test-invite-code", follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn('id="register-form"', r.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
