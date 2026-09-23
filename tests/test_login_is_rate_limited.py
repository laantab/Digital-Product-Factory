"""Guessing a password must get slower, not stay free.

/auth/login accepted unlimited attempts. bcrypt at 12 rounds makes each guess
slow, which is a cost to the attacker but also an unmetered CPU bill on a
starter plan -- a few hundred parallel guesses is a denial of service as well as
a guessing run.

Two counters, because one is not enough on its own: too many failures from one
address, and too many failures against one account from one address. Keying on
the account alone would let anyone lock a real customer out of their own login.
A successful sign-in clears the counters for that pair.
"""
import os
import unittest

os.environ.setdefault("FACTORY_TEST_MODE", "1")

import database  # noqa: E402
from app import app  # noqa: E402
from routes import auth as auth_routes  # noqa: E402

PW = "a-good-enough-password"


class LoginIsRateLimitedTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from unittest import mock

        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._old_db = database.DB_PATH
        database.DB_PATH = self._tmp.name
        database.init_db()
        patcher = mock.patch.object(auth_routes, "_BCRYPT_ROUNDS", 4)
        patcher.start()
        self.addCleanup(patcher.stop)
        database.create_user("real@example.com", auth_routes._hash_password(PW), role="user")
        auth_routes.reset_login_attempts()
        self.addCleanup(auth_routes.reset_login_attempts)
        app.config["TESTING"] = True
        self.client = app.test_client()

    def tearDown(self):
        database.DB_PATH = self._old_db
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(self._tmp.name + suffix)
            except OSError:
                pass

    def _attempt(self, password, email="real@example.com", ip="203.0.113.9"):
        return self.client.post(
            "/auth/login",
            json={"email": email, "password": password},
            headers={"X-Forwarded-For": ip},
        )

    def test_a_few_wrong_guesses_are_still_just_refused(self):
        for _ in range(3):
            self.assertEqual(self._attempt("wrong").status_code, 401)

    def test_a_run_of_wrong_guesses_is_eventually_refused_with_429(self):
        seen = [self._attempt("wrong").status_code for _ in range(25)]
        self.assertIn(429, seen, "a password could be guessed at forever")
        self.assertLess(seen.index(429), 20, f"the limit let too many through: {seen}")

    def test_the_lockout_says_how_long_to_wait(self):
        for _ in range(25):
            r = self._attempt("wrong")
            if r.status_code == 429:
                break
        self.assertEqual(r.status_code, 429)
        self.assertTrue(r.headers.get("Retry-After"), "no Retry-After on the refusal")
        self.assertNotIn("bcrypt", r.get_data(as_text=True).lower())

    def test_the_right_password_still_works_before_the_limit(self):
        self._attempt("wrong")
        self.assertEqual(self._attempt(PW).status_code, 200)

    def test_signing_in_clears_the_count(self):
        for _ in range(5):
            self._attempt("wrong")
        self.assertEqual(self._attempt(PW).status_code, 200)
        for _ in range(5):
            self.assertEqual(self._attempt("wrong").status_code, 401)

    def test_one_attacker_cannot_lock_a_real_customer_out(self):
        """The victim signs in from their own address while the attacker is blocked."""
        for _ in range(25):
            self._attempt("wrong", ip="198.51.100.4")
        self.assertEqual(self._attempt("wrong", ip="198.51.100.4").status_code, 429)
        self.assertEqual(self._attempt(PW, ip="203.0.113.77").status_code, 200)

    def test_spraying_many_accounts_from_one_address_is_also_stopped(self):
        seen = []
        for i in range(40):
            seen.append(self._attempt("wrong", email=f"person{i}@example.com").status_code)
        self.assertIn(429, seen, "one address could try one guess against every account")


if __name__ == "__main__":
    unittest.main()
