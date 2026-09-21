"""Phase A login and project ownership, forward-ported for Factory 1.8.5.

Every test runs against its OWN fresh SQLite file (database.DB_PATH is
patched), so ids are deterministic and no real database is touched.
Passwords used here are throwaway test values; no real password appears.
"""
from __future__ import annotations

import os
import sqlite3
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


class _FreshDb(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(self.path)
        for p in (patch.object(database, "DB_PATH", self.path),
                  patch.object(database, "_use_postgres", return_value=False),
                  patch.object(auth_routes, "_BCRYPT_ROUNDS", 4),
                  patch.object(app_module, "_invite_code_required", return_value="")):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(lambda: [os.path.exists(x) and os.unlink(x)
                                 for x in (self.path, self.path + "-wal", self.path + "-shm")])
        database.init_db()
        self.client = app_module.app.test_client()

    def register(self, email, password=PW, client=None):
        return (client or self.client).post("/auth/register",
                                            json={"email": email, "password": password})

    def login(self, email, password=PW, client=None):
        return (client or self.client).post("/auth/login",
                                            json={"email": email, "password": password})


class RegistrationAndLoginTests(_FreshDb):

    def test_first_account_is_admin_then_users(self):
        a = self.register("owner@example.com").get_json()
        b = self.register("second@example.com", client=app_module.app.test_client()).get_json()
        self.assertEqual(a["user"]["role"], "admin")
        self.assertEqual(b["user"]["role"], "user")

    def test_password_is_hashed_and_never_returned(self):
        r = self.register("owner@example.com")
        self.assertEqual(r.status_code, 201)
        body = r.get_data(as_text=True)
        self.assertNotIn(PW, body)
        self.assertNotIn("password", body.lower())
        stored = database.get_user_by_email("owner@example.com")["password_hash"]
        self.assertTrue(stored.startswith("$2"), "not a bcrypt hash")
        self.assertNotIn(PW, stored)

    def test_login_logout_me(self):
        self.register("owner@example.com")
        c = app_module.app.test_client()
        self.assertEqual(c.get("/auth/me").status_code, 401)
        self.assertEqual(self.login("owner@example.com", client=c).status_code, 200)
        me = c.get("/auth/me").get_json()
        self.assertEqual(me["user"]["email"], "owner@example.com")
        self.assertNotIn("password_hash", me["user"])
        self.assertEqual(c.post("/auth/logout").status_code, 200)
        self.assertEqual(c.get("/auth/me").status_code, 401)

    def test_wrong_password_and_unknown_email_look_the_same(self):
        self.register("owner@example.com")
        c = app_module.app.test_client()
        a = self.login("owner@example.com", "wrong-password-9", client=c)
        b = self.login("nobody@example.com", client=c)
        self.assertEqual(a.status_code, 401)
        self.assertEqual(a.get_json(), b.get_json())

    def test_duplicate_and_invalid_registration(self):
        self.register("owner@example.com")
        c = app_module.app.test_client()
        self.assertEqual(self.register("OWNER@example.com", client=c).status_code, 409)
        self.assertEqual(self.register("not-an-email", client=c).status_code, 400)
        self.assertEqual(self.register("x@example.com", "short", client=c).status_code, 400)

    def test_inactive_user_cannot_log_in_and_loses_an_existing_session(self):
        uid = self.register("owner@example.com").get_json()["user"]["id"]
        self.assertEqual(self.client.get("/auth/me").status_code, 200)
        database.set_user_active(uid, False)
        self.assertEqual(self.client.get("/auth/me").status_code, 401,
                         "a deactivated user kept a working session")
        self.assertEqual(self.login("owner@example.com",
                                    client=app_module.app.test_client()).status_code, 403)


class StableIdentityTests(_FreshDb):

    def test_lonnie_is_user_2_without_exposing_the_password(self):
        # Same shape as the Phase A database: a placeholder admin first (id 1),
        # then Lonnie's real account (id 2), promoted to admin.
        database.create_user("placeholder@factory.local",
                             auth_routes._hash_password("placeholder-only-1"), role="admin")
        row = database.create_user("lonnie@gmail.com",
                                   auth_routes._hash_password(PW), role="admin")
        self.assertEqual(row["id"], 2)
        r = self.login("lonnie@gmail.com")
        self.assertEqual(r.get_json()["user"], {"id": 2, "email": "lonnie@gmail.com",
                                                "role": "admin"})
        me = self.client.get("/auth/me").get_data(as_text=True)
        self.assertNotIn(PW, me)
        self.assertNotIn("$2", me, "the password hash reached the browser")


class OwnershipTests(_FreshDb):

    def _project(self, name="Container Gardening for Beginners"):
        return database.create_project(name, "ebook", {"title": name},
                                       user_saved=True, user_confirmed_save=True)

    def test_creating_the_schema_changes_no_existing_project(self):
        p = self._project()
        before = database.get_project(p["id"])
        database.init_db()
        database.init_db()
        after = database.get_project(p["id"])
        self.assertEqual(before["name"], after["name"])
        self.assertEqual(before["data"], after["data"])
        self.assertIsNone(database.get_project_owner(p["id"]))

    def test_backfill_assigns_only_unowned_and_is_repeatable(self):
        owner = database.create_user("owner@example.com",
                                     auth_routes._hash_password(PW), role="admin")
        other = database.create_user("other@example.com",
                                     auth_routes._hash_password(PW))
        a, b, c = self._project("A"), self._project("B"), self._project("C")
        database.set_project_owner(c["id"], other["id"])
        self.assertEqual(database.backfill_project_owners(owner["id"]), 2)
        self.assertEqual(database.backfill_project_owners(owner["id"]), 0,
                         "a second run changed rows")
        self.assertEqual(database.get_project_owner(a["id"]), owner["id"])
        self.assertEqual(database.get_project_owner(c["id"]), other["id"],
                         "an owned project was reassigned")
        counts = database.ownership_counts()
        self.assertEqual((counts["projects"], counts["unowned"]), (3, 0))

    def test_project_ids_and_count_survive_the_migration_script(self):
        from scripts.migrate_phase_a import run

        ids = [self._project(f"P{i}")["id"] for i in range(5)]
        owner = database.create_user("owner@example.com",
                                     auth_routes._hash_password(PW), role="admin")
        first = run(owner_email="owner@example.com")
        second = run(owner_email="owner@example.com")
        self.assertEqual(first["assigned"], 5)
        self.assertEqual(second["assigned"], 0)
        self.assertEqual(sorted(p["id"] for p in database.list_projects(include_system=True)
                                if p["id"] in ids), sorted(ids))
        self.assertEqual(database.count_users(), 1, "the migration created a user")
        self.assertTrue(all(database.get_project_owner(i) == owner["id"] for i in ids))

    def test_report_only_run_changes_nothing(self):
        from scripts.migrate_phase_a import run

        p = self._project()
        r = run()
        self.assertEqual(r["assigned"], 0)
        self.assertIsNone(database.get_project_owner(p["id"]))

    def test_owner_must_exist(self):
        p = self._project()
        self.assertFalse(database.set_project_owner(p["id"], 999))
        with self.assertRaises(ValueError):
            database.backfill_project_owners(999)


class AdminAndInviteTests(_FreshDb):

    def test_admin_required_decorator(self):
        from flask import Flask
        from flask_login import LoginManager
        from auth import admin_required, load_user

        mini = Flask("mini")
        mini.config["SECRET_KEY"] = "test"
        lm = LoginManager(mini)
        lm.user_loader(load_user)
        mini.register_blueprint(auth_routes.auth_bp)

        @mini.get("/admin-only")
        @admin_required
        def admin_only():
            return "ok"

        c = mini.test_client()
        self.assertEqual(c.get("/admin-only").status_code, 401)
        self.register("admin@example.com", client=c)            # first user: admin
        self.assertEqual(c.get("/admin-only").status_code, 200)
        c2 = mini.test_client()
        self.register("user@example.com", client=c2)            # second: user
        self.assertEqual(c2.get("/admin-only").status_code, 403)

    def test_invite_gate_still_runs_before_login(self):
        with patch.object(app_module, "_invite_code_required", return_value="beta-code"):
            c = app_module.app.test_client()
            r = c.post("/auth/login", json={"email": "a@example.com", "password": PW})
            self.assertEqual(r.status_code, 401)
            self.assertNotIn("Invalid email", r.get_data(as_text=True),
                             "the login route answered before the invite gate")

    def test_no_hardcoded_secret_key(self):
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("dev-change-me", src)
        self.assertTrue(app_module.app.config.get("SECRET_KEY"))


if __name__ == "__main__":
    unittest.main()
