"""Saved Projects — only user-saved completed products with downloadable output.

Zero paid/external calls. Uses Flask test client + live DB + source inspection.
Does not delete real products (#4249, #14626). Cleans up rows this test creates.
"""
from __future__ import annotations

import os
import shutil
import sys
import unittest
import uuid
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("FACTORY_TEST_MODE", "1")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("TAVILY_API_KEY", "")

from app import app  # noqa: E402
import database  # noqa: E402
from tests._test_paths import resolve_test_exports_root  # noqa: E402


FORBIDDEN = (
    "guided cover isolated",
    "seed self refuse",
    "research: view only",
    "research persist",
    "needs correction",
)


def _normalize(name: str) -> str:
    return " ".join((name or "").strip().lower().split())


class SavedProjectsLast10Tests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True
        self._created_ids: list[int] = []
        self._export_dirs: list[Path] = []

    def tearDown(self):
        for pid in self._created_ids:
            try:
                database.delete_project(pid)
            except Exception:
                pass
        for folder in self._export_dirs:
            shutil.rmtree(folder, ignore_errors=True)

    def _names(self, path):
        resp = self.client.get(path)
        self.assertEqual(resp.status_code, 200, resp.data)
        rows = resp.get_json() or []
        self.assertIsInstance(rows, list)
        return rows, [p.get("name") or "" for p in rows]

    def _write_outputs(self) -> str:
        pkg = f"test-saved-{uuid.uuid4().hex[:12]}"
        folder = resolve_test_exports_root() / pkg
        folder.mkdir(parents=True, exist_ok=True)
        self._export_dirs.append(folder)
        (folder / "product.pdf").write_bytes(b"%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF\n")
        with zipfile.ZipFile(folder / "package.zip", "w") as zf:
            zf.writestr("product.pdf", b"%PDF-1.4\n%%EOF\n")
        return pkg

    def _post(self, payload):
        resp = self.client.post("/projects", json=payload)
        self.assertEqual(resp.status_code, 201, resp.data)
        body = resp.get_json()
        pid = int(body["id"])
        self._created_ids.append(pid)
        return pid, body

    def _complete_payload(self, name, pkg, **extra):
        data = {
            "title": name,
            "product_type": "coloring_book",
            "status": "export_ready",
            "stage": "export_ready",
            "user_confirmed_save": True,
            "package_id": pkg,
            "pdf_available": True,
            "zip_available": True,
            "pdf_path": f"exports/{pkg}/product.pdf",
            "zip_path": f"exports/{pkg}/package.zip",
        }
        data.update(extra)
        return {
            "name": name,
            "type": "product",
            "data": data,
            "user_saved": True,
            "user_confirmed_save": True,
        }

    def test_customer_list_limit_dedupe_and_hide(self):
        rows, names = self._names("/projects")
        self.assertLessEqual(len(rows), 10)
        lowered = " | ".join(names).lower()
        for needle in FORBIDDEN:
            self.assertNotIn(needle, lowered, needle)
        counts = Counter(_normalize(n) for n in names)
        for title, count in counts.items():
            self.assertEqual(count, 1, f"duplicate title {title}")
        stamps = [str(p.get("updated_at") or "") for p in rows]
        self.assertEqual(stamps, sorted(stamps, reverse=True))

        hidden = self.client.post(
            "/projects",
            json={
                "name": "Guided Cover Isolated Test",
                "type": "ebook",
                "data": {"title": "Guided Cover Isolated Test"},
                "user_saved": True,
            },
        )
        self.assertEqual(hidden.status_code, 201, hidden.data)
        hidden_id = int(hidden.get_json()["id"])
        self._created_ids.append(hidden_id)
        rows, names = self._names("/projects")
        self.assertLessEqual(len(rows), 10)
        self.assertNotIn(hidden_id, {int(p["id"]) for p in rows})
        self.assertFalse(any("guided cover isolated" in n.lower() for n in names))

        pkg = self._write_outputs()
        real_id, _ = self._post(self._complete_payload("Customer Saved Completed Product", pkg))
        rows, names = self._names("/projects")
        self.assertIn(real_id, {int(p["id"]) for p in rows})
        self.assertIn("Customer Saved Completed Product", names)
        self.assertLessEqual(len(rows), 10)

    def test_needs_correction_excluded(self):
        pkg = self._write_outputs()
        pid, _ = self._post(
            self._complete_payload(
                "Needs Correction Customer Probe",
                pkg,
                status="needs_correction",
                stage="needs_correction",
                status_label="Needs correction.",
                quality_blocking=True,
                pdf_available=False,
            )
        )
        ids, names = self._ids("/projects")
        self.assertNotIn(pid, ids)
        self.assertFalse(any("needs correction customer probe" in n.lower() for n in names))
        self.assertIsNotNone(database.get_project(pid))

    def test_research_and_product_plans_excluded(self):
        research = self.client.post(
            "/projects",
            json={
                "name": "Customer Research Plan Keep Check",
                "type": "research_plan",
                "data": {"status": "research_saved", "user_confirmed_save": True},
                "user_saved": True,
                "user_confirmed_save": True,
            },
        )
        plan = self.client.post(
            "/projects",
            json={
                "name": "Customer Product Plan Keep Check",
                "type": "product_plan",
                "data": {"status": "product_plan_saved", "user_confirmed_save": True},
                "user_saved": True,
                "user_confirmed_save": True,
            },
        )
        self.assertEqual(research.status_code, 201, research.data)
        self.assertEqual(plan.status_code, 201, plan.data)
        rid = int(research.get_json()["id"])
        pid = int(plan.get_json()["id"])
        self._created_ids.extend([rid, pid])
        ids, names = self._ids("/projects")
        self.assertNotIn(rid, ids)
        self.assertNotIn(pid, ids)
        joined = " | ".join(names).lower()
        self.assertNotIn("customer research plan keep check", joined)
        self.assertNotIn("customer product plan keep check", joined)

    def test_no_downloadable_output_excluded(self):
        pid, _ = self._post(
            {
                "name": "Customer Real Product Check Search",
                "type": "product",
                "data": {
                    "title": "Customer Real Product Check Search",
                    "status": "export_ready",
                    "user_confirmed_save": True,
                },
                "user_saved": True,
                "user_confirmed_save": True,
            }
        )
        ids, names = self._ids("/projects")
        self.assertNotIn(pid, ids)
        self.assertFalse(any("customer real product check search" in n.lower() for n in names))

    def test_no_user_confirmed_save_excluded(self):
        pkg = self._write_outputs()
        pid, _ = self._post(
            {
                "name": "Unconfirmed Complete Output Probe",
                "type": "product",
                "data": {
                    "title": "Unconfirmed Complete Output Probe",
                    "product_type": "coloring_book",
                    "status": "export_ready",
                    "stage": "export_ready",
                    "package_id": pkg,
                    "pdf_available": True,
                    "zip_available": True,
                    "pdf_path": f"exports/{pkg}/product.pdf",
                },
                "user_saved": True,
            }
        )
        ids, _ = self._ids("/projects")
        self.assertNotIn(pid, ids)

    def test_limit_10_not_padded(self):
        before_rows, _ = self._names("/projects")
        self.assertLessEqual(len(before_rows), 10)
        for i in range(3):
            self._post(
                {
                    "name": f"Padding Workflow Record {i}",
                    "type": "product",
                    "data": {"title": f"Padding Workflow Record {i}", "status": "draft"},
                    "user_saved": True,
                    "user_confirmed_save": True,
                }
            )
        after_rows, names = self._names("/projects")
        self.assertEqual(len(after_rows), len(before_rows))
        self.assertLessEqual(len(after_rows), 10)
        self.assertFalse(any("padding workflow record" in n.lower() for n in names))

    def test_dashboard_limit_3_same_filter(self):
        dash_rows, dash_names = self._names("/projects?limit=3")
        full_rows, full_names = self._names("/projects")
        self.assertLessEqual(len(dash_rows), 3)
        self.assertEqual(dash_names, full_names[: len(dash_names)])
        lowered = " | ".join(dash_names).lower()
        for needle in FORBIDDEN:
            self.assertNotIn(needle, lowered, needle)
        src = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("/projects?limit=3", src)
        self.assertIn("get_customer_saved_products", (ROOT / "database.py").read_text(encoding="utf-8"))

    def test_admin_full_list(self):
        admin_rows, _ = self._names("/projects?admin=1")
        customer_rows, _ = self._names("/projects")
        self.assertGreater(len(admin_rows), len(customer_rows))
        self.assertGreater(len(admin_rows), 10)

    def test_open_pdf_zip_still_present(self):
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('data-open>Open</button>', js)
        self.assertIn("Download PDF", js)
        self.assertIn("Download ZIP", js)
        self.assertIn("get_customer_saved_products", (ROOT / "database.py").read_text(encoding="utf-8"))
        self.assertIn("Do you want to save this product?", js)
        self.assertIn(">Save Product</button>", js)
        self.assertIn("Continue Without Saving", js)
        self.assertIn("/projects?limit=3", js)
        self.assertIn("q.get(\"admin\") === \"1\"", js)
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Your latest saved products are listed below. Download the files you want to keep.", html)
        self.assertIn("Showing up to 10 of your saved products.", html)
        self.assertNotIn("Showing your 10 most recent saved products.", html)
        self.assertIn("View older projects", html)
        saved_section = html.split('data-view="saved"', 1)[1].split('data-view="research"', 1)[0]
        self.assertNotIn("Search saved products", saved_section)
        self.assertIn("admin-controls hidden", saved_section)
        self.assertIn("_coloringBookPendingApproval", js)
        self.assertIn("_coloringBookCustomerReady", js)
        self.assertIn("_coloringBookInteriorPreviewHtml", js)
        self.assertIn("Your cover stays on this page while the next step runs", js)
        self.assertIn("Save stays disabled until the complete coloring book passes quality checks", js)
        self.assertIn("if (!_coloringBookPendingApproval(data) && _coloringBookCustomerReady(data))", js)
        self.assertIn("data-coloring-interior-preview", js)

    def test_no_delete_of_real_products_by_filter(self):
        before_4249 = database.get_project(4249)
        before_14626 = database.get_project(14626)
        conn = database.get_conn()
        total_before = conn.execute("select count(*) from projects").fetchone()[0]
        conn.close()
        rows, names = self._names("/projects")
        after_4249 = database.get_project(4249)
        after_14626 = database.get_project(14626)
        conn = database.get_conn()
        total_after = conn.execute("select count(*) from projects").fetchone()[0]
        conn.close()
        self.assertEqual(total_before, total_after)
        self.assertEqual(before_4249 is None, after_4249 is None)
        if before_4249:
            self.assertEqual(before_4249["id"], after_4249["id"])
            self.assertEqual(before_4249["name"], after_4249["name"])
            self.assertEqual(before_4249.get("data"), after_4249.get("data"))
        if before_14626:
            self.assertEqual(before_14626["id"], after_14626["id"])
            self.assertEqual(before_14626["name"], after_14626["name"])
        ids = {int(p["id"]) for p in rows}
        if before_4249 and database.is_customer_keep_product(after_4249):
            self.assertIn(4249, ids)
        if before_14626 and database.is_customer_keep_product(after_14626):
            self.assertIn(14626, ids)
        self.assertLessEqual(len(rows), 10)

    def test_function_does_not_write_rows(self):
        conn = database.get_conn()
        total_before = conn.execute("select count(*) from projects").fetchone()[0]
        conn.close()
        database.get_customer_saved_products(limit=10)
        database.get_customer_saved_projects(limit=10)
        conn = database.get_conn()
        total_after = conn.execute("select count(*) from projects").fetchone()[0]
        conn.close()
        self.assertEqual(total_before, total_after)

    def test_coloring_book_draft_artifact_state_listed(self):
        """Complete coloring books stay artifact_state=DRAFT until locked.

        That write-policy flag must not hide them from Saved Projects.
        """
        pkg = self._write_outputs()
        pid, _ = self._post(
            self._complete_payload(
                "Sea Creatures Listed Despite Draft Artifact",
                pkg,
                artifact_state="DRAFT",
                generation_stage="full",
                qa_passed=True,
            )
        )
        ids, names = self._ids("/projects")
        self.assertIn(pid, ids)
        self.assertIn("Sea Creatures Listed Despite Draft Artifact", names)

    def test_coloring_book_cover_preview_stage_excluded(self):
        pkg = self._write_outputs()
        pid, _ = self._post(
            self._complete_payload(
                "Sea Creatures Cover Only Probe",
                pkg,
                artifact_state="DRAFT",
                generation_stage="cover_preview",
                needs_approval=True,
                qa_passed=True,
            )
        )
        ids, names = self._ids("/projects")
        self.assertNotIn(pid, ids)
        self.assertFalse(any("sea creatures cover only probe" in n.lower() for n in names))
        self.assertIsNotNone(database.get_project(pid))

    def test_crossword_and_word_search_draft_artifact_still_listed(self):
        pkg = self._write_outputs()
        cw_id, _ = self._post(
            {
                "name": "Draft Artifact Crossword Keep Check",
                "type": "product",
                "data": {
                    "title": "Draft Artifact Crossword Keep Check",
                    "product_type": "crossword",
                    "status": "export_ready",
                    "stage": "export_ready",
                    "artifact_state": "DRAFT",
                    "user_confirmed_save": True,
                    "package_id": pkg,
                    "pdf_available": True,
                    "zip_available": True,
                    "pdf_path": f"exports/{pkg}/product.pdf",
                    "zip_path": f"exports/{pkg}/package.zip",
                },
                "user_saved": True,
                "user_confirmed_save": True,
            }
        )
        ws_id, _ = self._post(
            {
                "name": "Draft Artifact Word Search Keep Check",
                "type": "product",
                "data": {
                    "title": "Draft Artifact Word Search Keep Check",
                    "product_type": "word_search",
                    "status": "product_generated",
                    "stage": "product_generated",
                    "artifact_state": "DRAFT",
                    "user_confirmed_save": True,
                    "package_id": pkg,
                    "pdf_available": True,
                    "pdf_path": f"exports/{pkg}/product.pdf",
                },
                "user_saved": True,
                "user_confirmed_save": True,
            }
        )
        ids, names = self._ids("/projects")
        self.assertIn(cw_id, ids)
        self.assertIn(ws_id, ids)
        self.assertIn("Draft Artifact Crossword Keep Check", names)
        self.assertIn("Draft Artifact Word Search Keep Check", names)

    def test_live_deep_sea_ocean_creatures_is_customer_saved(self):
        """Project 17365 is the real Sea Creatures attempt. Do not mutate it."""
        live = database.get_project(17365)
        self.assertIsNotNone(live, "project 17365 must exist (see tests/fixtures/frozen_project_17365.json)")
        self.assertEqual(live["name"], "Deep Sea Ocean Creatures")
        data = live.get("data") or {}
        self.assertEqual(data.get("product_type"), "coloring_book")
        self.assertEqual(data.get("artifact_state"), "DRAFT")
        self.assertTrue(database.is_customer_saved_product(live))
        self.assertTrue(database._customer_status_allows_saved_list(live))
        self.assertTrue(database._coloring_book_ready_for_customer_list(live))

    def test_customer_check_titles_without_output_hidden(self):
        _, names = self._names("/projects")
        lowered = " | ".join(names).lower()
        self.assertNotIn("customer real product check search", lowered)
        self.assertNotIn("customer real product check", lowered)

    def _ids(self, path):
        rows, names = self._names(path)
        return {int(p["id"]) for p in rows}, names


if __name__ == "__main__":
    unittest.main()
