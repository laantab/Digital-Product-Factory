"""Phase B2 — Pin Factory Pro proxy (Factory 1.8.5).

Proves:
  - /pin-factory/* needs a logged-in, ACTIVE Factory user (401/403 otherwise).
  - X-Factory-User-ID is always str(current_user.id). Nothing the browser
    sends -- header, query string, JSON body, cookie -- can change it.
  - X-Internal-API-Key is added on the server and never reaches the browser
    (body, headers, error text, logs).
  - Unsafe request headers are not forwarded; only allow-listed response
    headers come back; upstream redirects are refused.
  - Upstream failures are controlled JSON errors with no stack trace.

No real network call is made: requests.request is replaced in every test.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("FACTORY_TEST_MODE", "1")

import app as app_module  # noqa: E402
import database  # noqa: E402
import routes.auth as auth_routes  # noqa: E402

KEY = "test-internal-key-7f3a9c"
BASE = "http://pin-factory.test/api"
PW = "test-only-pass-123"
ROUTES = ("text", "image", "export", "microtools", "health")


class _Upstream:
    def __init__(self, status=200, body=None, headers=None, raise_exc=None):
        self.status, self.body = status, body or {"ok": True}
        self.headers, self.raise_exc = headers or {}, raise_exc
        self.calls = []

    def __call__(self, method, url, **kw):
        self.calls.append({"method": method, "url": url, **kw})
        if self.raise_exc:
            raise self.raise_exc
        r = MagicMock()
        r.status_code = self.status
        r.headers = {"Content-Type": "application/json", **self.headers}
        r.content = json.dumps(self.body).encode()
        return r

    @property
    def last(self):
        return self.calls[-1]


class _Case(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(self.path)
        self.upstream = _Upstream()
        for p in (patch.object(database, "DB_PATH", self.path),
                  patch.object(database, "_use_postgres", return_value=False),
                  patch.object(auth_routes, "_BCRYPT_ROUNDS", 4),
                  patch.object(app_module, "_invite_code_required", return_value=""),
                  patch.dict(os.environ, {"PIN_FACTORY_BASE_URL": BASE,
                                          "PIN_FACTORY_INTERNAL_KEY": KEY}),
                  patch("services.pin_factory_proxy.requests.request", self.upstream)):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(lambda: [os.path.exists(x) and os.unlink(x)
                                 for x in (self.path, self.path + "-wal", self.path + "-shm")])
        database.init_db()
        # id 1 = someone else, id 2 = the user under test
        database.create_user("first@example.com", auth_routes._hash_password(PW), role="admin")
        self.uid = database.create_user("member@example.com",
                                        auth_routes._hash_password(PW), role="admin")["id"]
        self.anon = app_module.app.test_client()
        self.client = app_module.app.test_client()
        r = self.client.post("/auth/login", json={"email": "member@example.com", "password": PW})
        assert r.status_code == 200, r.get_data(as_text=True)


class AccessTests(_Case):

    def test_every_route_refuses_a_visitor_who_is_not_logged_in(self):
        for name in ROUTES:
            r = self.anon.get(f"/pin-factory/{name}")
            self.assertEqual(r.status_code, 401, name)
        self.assertEqual(self.upstream.calls, [], "an anonymous request reached Pin Factory")

    def test_an_inactive_user_is_refused(self):
        database.set_user_active(self.uid, False)
        r = self.client.get("/pin-factory/health")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.upstream.calls, [])

    def test_the_invite_gate_still_runs_first(self):
        with patch.object(app_module, "_invite_code_required", return_value="beta-code"):
            r = self.client.get("/pin-factory/health")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.upstream.calls, [])

    def test_all_five_routes_exist_and_proxy(self):
        for name in ROUTES:
            method = "get" if name == "health" else "post"
            r = getattr(self.client, method)(f"/pin-factory/{name}", json={})
            self.assertEqual(r.status_code, 200, name)
            self.assertEqual(self.upstream.last["url"], f"{BASE}/{name}")


class IdentityTests(_Case):

    def _sent_id(self):
        return self.upstream.last["headers"].get("X-Factory-User-ID")

    def test_identity_is_current_user_id(self):
        self.client.get("/pin-factory/health")
        self.assertEqual(self._sent_id(), str(self.uid))

    def test_browser_header_cannot_impersonate(self):
        self.client.get("/pin-factory/health",
                        headers={"X-Factory-User-ID": "1", "X-Factory-Account": "1"})
        self.assertEqual(self._sent_id(), str(self.uid))

    def test_query_string_cannot_impersonate(self):
        self.client.get("/pin-factory/health?user_id=1&account_ref=1&keep=yes")
        url = self.upstream.last["url"]
        self.assertNotIn("user_id", url)
        self.assertNotIn("account_ref", url)
        self.assertIn("keep=yes", url)
        self.assertEqual(self._sent_id(), str(self.uid))

    def test_json_body_cannot_impersonate(self):
        self.client.post("/pin-factory/text",
                         json={"user_id": 1, "factory_user_id": "1", "prompt": "herbs"})
        sent = json.loads(self.upstream.last["data"])
        self.assertEqual(sent, {"prompt": "herbs"})
        self.assertEqual(self._sent_id(), str(self.uid))

    def test_cookie_cannot_impersonate(self):
        self.client.set_cookie("user_id", "1")
        self.client.get("/pin-factory/health")
        self.assertEqual(self._sent_id(), str(self.uid))
        self.assertNotIn("Cookie", self.upstream.last["headers"])

    def test_the_proxy_itself_refuses_a_missing_identity(self):
        from services.pin_factory_proxy import proxy_pin_factory

        with app_module.app.test_request_context("/pin-factory/health"):
            from flask import request

            body, status, _ = proxy_pin_factory(request, "health", lambda *a: None,
                                                factory_user_id="")
        self.assertEqual(status, 401)
        self.assertNotIn(b"anonymous", body)


class SecretTests(_Case):

    def test_key_is_sent_upstream(self):
        self.client.get("/pin-factory/health")
        self.assertEqual(self.upstream.last["headers"].get("X-Internal-API-Key"), KEY)

    def test_key_never_reaches_the_browser(self):
        self.upstream.headers = {"X-Internal-API-Key": KEY, "X-Internal-Debug": KEY}
        r = self.client.get("/pin-factory/health")
        self.assertNotIn(KEY, r.get_data(as_text=True))
        self.assertNotIn(KEY, json.dumps(dict(r.headers)))

    def test_key_not_in_error_responses_or_logs(self):
        self.upstream.raise_exc = requests.ConnectionError(f"boom {KEY}")
        with self.assertLogs(app_module.app.logger, level="INFO") as logs:
            r = self.client.get("/pin-factory/health")
        self.assertEqual(r.status_code, 503)
        self.assertNotIn(KEY, r.get_data(as_text=True))
        self.assertNotIn(KEY, "\n".join(logs.output))

    def test_missing_key_means_not_configured_and_no_request(self):
        with patch.dict(os.environ, {"PIN_FACTORY_INTERNAL_KEY": ""}):
            r = self.client.get("/pin-factory/health")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(self.upstream.calls, [])

    def test_missing_base_url_means_not_configured(self):
        with patch.dict(os.environ, {"PIN_FACTORY_BASE_URL": ""}):
            r = self.client.get("/pin-factory/health")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(self.upstream.calls, [])


class HeaderTests(_Case):

    def test_unsafe_request_headers_are_not_forwarded(self):
        self.client.get("/pin-factory/health", headers={
            "Authorization": "Bearer x", "X-Forwarded-For": "1.2.3.4",
            "X-Internal-API-Key": "forged", "Accept": "application/json"})
        sent = self.upstream.last["headers"]
        self.assertNotIn("Authorization", sent)
        self.assertNotIn("X-Forwarded-For", sent)
        self.assertEqual(sent["X-Internal-API-Key"], KEY, "a browser forged the key header")
        self.assertEqual(sent.get("Accept"), "application/json")

    def test_only_allow_listed_response_headers_come_back(self):
        self.upstream.headers = {"Set-Cookie": "pfp=1", "Location": "http://internal:3000/x",
                                 "Content-Encoding": "gzip", "Content-Length": "999",
                                 "Cache-Control": "no-store"}
        r = self.client.get("/pin-factory/health")
        for h in ("Set-Cookie", "Location", "Content-Encoding"):
            self.assertNotIn(h, r.headers, h)
        self.assertEqual(r.headers.get("Cache-Control"), "no-store")

    def test_upstream_redirect_is_refused(self):
        self.upstream.status = 302
        self.upstream.headers = {"Location": "http://internal:3000/login"}
        r = self.client.get("/pin-factory/health")
        self.assertEqual(r.status_code, 502)
        self.assertNotIn("internal:3000", r.get_data(as_text=True))
        self.assertFalse(self.upstream.last["allow_redirects"])


class ForwardingTests(_Case):

    def test_status_codes_and_body_preserved(self):
        self.upstream.status, self.upstream.body = 400, {"ok": False, "error": "bad"}
        r = self.client.post("/pin-factory/text", json={"prompt": "x"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json(), {"ok": False, "error": "bad"})

    def test_method_and_timeouts(self):
        self.client.post("/pin-factory/export", json={"a": 1})
        self.assertEqual(self.upstream.last["method"], "POST")
        self.assertEqual(self.upstream.last["timeout"], (10, 20))

    def test_timeout_is_a_controlled_503(self):
        self.upstream.raise_exc = requests.Timeout("slow")
        r = self.client.get("/pin-factory/health")
        self.assertEqual(r.status_code, 503)
        self.assertNotIn("Traceback", r.get_data(as_text=True))


class PathSafetyTests(unittest.TestCase):

    def test_traversal_and_foreign_hosts_are_rejected(self):
        from services.pin_factory_proxy import _build_upstream_url, _is_safe_target_path

        for bad in ("", "../admin", "/etc/passwd", "a/../../b"):
            self.assertFalse(_is_safe_target_path(bad), bad)
        self.assertEqual(_build_upstream_url("ftp://pfp.test", "text"), "")
        self.assertEqual(_build_upstream_url(BASE, "text"), f"{BASE}/text")
        self.assertEqual(_build_upstream_url(BASE, "@evil.test/x"),
                         f"{BASE}/@evil.test/x")  # stays on the configured host


if __name__ == "__main__":
    unittest.main()
