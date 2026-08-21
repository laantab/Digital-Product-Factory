"""Saved Projects customer view — last 10 unique real products.

Zero paid/external calls. Uses Flask test client + source inspection.
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
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("TAVILY_API_KEY", "")

from app import app  # noqa: E402
import database  # noqa: E402


class SavedProjectsHardCleanupTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True

    def _ids(self, resp):
        self.assertEqual(resp.status_code, 200, resp.data)
        rows = resp.get_json() or []
        self.assertIsInstance(rows, list)
        return {int(p["id"]) for p in rows}, [p.get("name") or "" for p in rows]

    def test_a_normal_view_hides_internal_and_keeps_real(self):
        hidden_specs = [
            ("Guided Cover Isolated", "ebook"),
            ("Seed Self Refuse", "ebook"),
            ("Research: view only", "research_plan"),
            ("PIPELINE TEST Record", "product"),
            ("DEBUG workflow check", "product"),
            ("Workflow Test Pack", "product"),
        ]
        hidden_ids = []
        for name, type_ in hidden_specs:
            created = self.client.post(
                "/projects",
                json={"name": name, "type": type_, "data": {"title": name}, "user_saved": True},
            )
            self.assertEqual(created.status_code, 201, created.data)
            body = created.get_json()
            hidden_ids.append(int(body["id"]))

        real = self.client.post(
            "/projects",
            json={
                "name": "Customer Real Product Check",
                "type": "product",
                "data": {"title": "Customer Real Product Check"},
                "user_saved": True,
                "user_confirmed_save": True,
            },
        )
        self.assertEqual(real.status_code, 201, real.data)
        real_id = int(real.get_json()["id"])

        ids, names = self._ids(self.client.get("/projects"))
        self.assertLessEqual(len(ids), 10)
        for hid in hidden_ids:
            self.assertNotIn(hid, ids)
        self.assertNotIn(real_id, ids)
        joined = " | ".join(names).lower()
        self.assertNotIn("guided cover isolated", joined)
        self.assertNotIn("seed self refuse", joined)
        self.assertNotIn("research: view only", joined)
        self.assertNotIn("customer real product check", joined)

    def test_b_admin_tools_are_not_customer_facing(self):
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Your latest saved products are listed below. Download the files you want to keep.", html)
        self.assertIn("admin-controls hidden", html)
        self.assertIn("Show test/debug/internal records", html)
        self.assertIn("Delete test/debug/internal records", html)
        self.assertIn("Delete all saved projects", html)
        self.assertIn('id="adminModeHint"', html)
        self.assertIn("function isAdminMode()", js)
        self.assertIn('q.get("admin") === "1"', js)
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        text = page.get_data(as_text=True)
        self.assertIn("admin-controls hidden", text)

    def test_c_new_internal_record_is_hidden(self):
        created = self.client.post(
            "/projects",
            json={
                "name": "Guided Cover Isolated Test",
                "type": "ebook",
                "data": {"title": "Guided Cover Isolated Test"},
                "user_saved": True,
            },
        )
        self.assertEqual(created.status_code, 201, created.data)
        body = created.get_json()
        ids, _ = self._ids(self.client.get("/projects"))
        self.assertNotIn(int(body["id"]), ids)
        admin_ids, _ = self._ids(self.client.get("/projects?include_system=1"))
        self.assertIn(int(body["id"]), admin_ids)

    def test_d_confirmed_real_product_without_output_is_hidden(self):
        created = self.client.post(
            "/projects",
            json={
                "name": "Customer Real Product Check",
                "type": "product",
                "data": {"title": "Customer Real Product Check", "product_type": "ebook"},
                "user_saved": True,
                "user_confirmed_save": True,
            },
        )
        self.assertEqual(created.status_code, 201, created.data)
        body = created.get_json()
        ids, names = self._ids(self.client.get("/projects"))
        self.assertNotIn(int(body["id"]), ids)
        self.assertFalse(any(n == "Customer Real Product Check" for n in names))
        self.assertLessEqual(len(ids), 10)

    def test_e_customer_search_clutter_removed(self):
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        saved = html.split('data-view="saved"', 1)[1].split("data-view=", 1)[0]
        self.assertNotIn('placeholder="Search saved products..."', saved)
        self.assertIn("get_customer_saved_products", (ROOT / "database.py").read_text(encoding="utf-8"))
        self.assertIn("get_customer_saved_products", (ROOT / "database.py").read_text(encoding="utf-8"))
        self.assertIn("get_customer_saved_projects", (ROOT / "database.py").read_text(encoding="utf-8"))
        self.assertIn("/projects?limit=3", js)
        self.assertIn("Showing up to 10 of your saved products.", html)
        hidden = self.client.post(
            "/projects",
            json={"name": "Guided Cover Isolated Search Probe", "type": "ebook", "data": {}},
        ).get_json()
        visible = self.client.post(
            "/projects",
            json={
                "name": "Customer Real Product Check Search",
                "type": "product",
                "data": {},
                "user_saved": True,
                "user_confirmed_save": True,
            },
        ).get_json()
        ids, names = self._ids(self.client.get("/projects"))
        self.assertNotIn(int(visible["id"]), ids)
        self.assertNotIn(int(hidden["id"]), ids)
        self.assertFalse(any("Customer Real Product Check Search" in n for n in names))
        self.assertFalse(any("Guided Cover Isolated Search Probe" in n for n in names))

    def test_locked_generators_and_hidden_menu_untouched(self):
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('label: "Marketing Kit"', js)
        self.assertIn('label: "Cover Design"', js)
        self.assertIn('label: "Flip Book"', js)
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Saved Projects", html)

    def test_classifier_is_conservative_on_real_titles(self):
        self.assertFalse(database.is_test_name("Latest Contest Ideas"))
        self.assertFalse(database.is_test_name("Immune System Health"))
        self.assertTrue(database.is_test_name("Guided Cover Isolated"))
        self.assertTrue(database.is_test_name("Seed Self Refuse"))
        self.assertTrue(database.is_test_name("Research: view only"))
        self.assertTrue(database.is_protected_customer_product(4249, "anything"))
        self.assertTrue(
            database.is_protected_customer_product(14626, "How to keep your teen safe online")
        )


if __name__ == "__main__":
    unittest.main()
