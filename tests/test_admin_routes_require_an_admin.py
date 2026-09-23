"""The two admin routes that copy and delete the database must not be open.

POST /admin/backup-db and DELETE /admin/delete-test-projects carried no
authentication of any kind. In production the invite gate stands in front of
them, but that is one shared code every pilot customer holds, so any customer --
or anyone they forward the code to -- could permanently delete rows from the
production database by visiting one URL. The delete runs against
`system_test = 1 OR temporary = 1 OR user_saved = 0`, and the name classifier
stamps those flags on real customer titles, so the rows at risk are real books.

/admin/storage-migration already had the right shape and is the model here.
"""
import os
import unittest

os.environ.setdefault("FACTORY_TEST_MODE", "1")


class AdminRoutesRequireAnAdminTests(unittest.TestCase):
    def setUp(self):
        import database
        from app import app

        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.app = app
        self.client = app.test_client()
        self.database = database

    def test_backup_is_refused_to_a_caller_who_is_not_logged_in(self):
        r = self.client.post("/admin/backup-db")
        self.assertIn(r.status_code, (401, 403, 404), r.get_data(as_text=True)[:200])

    def test_delete_is_refused_to_a_caller_who_is_not_logged_in(self):
        r = self.client.delete("/admin/delete-test-projects")
        self.assertIn(r.status_code, (401, 403, 404), r.get_data(as_text=True)[:200])

    def test_a_flagged_row_survives_an_unauthenticated_delete(self):
        """The point of the route is deletion, so prove nothing was deleted."""
        row = self.database.create_project(
            "Admin Guard Probe", "ebook", {"probe": True},
            system_test=True, temporary=True,
        )
        pid = row["id"]
        self.addCleanup(lambda: None)
        self.client.delete("/admin/delete-test-projects")
        self.assertIsNotNone(
            self.database.get_project(pid),
            "an unauthenticated caller deleted a row from the database",
        )

    def test_neither_route_answers_a_plain_get_either(self):
        for path in ("/admin/backup-db", "/admin/delete-test-projects"):
            r = self.client.get(path)
            self.assertNotEqual(r.status_code, 200, f"{path} answered a bare GET")


if __name__ == "__main__":
    unittest.main()
