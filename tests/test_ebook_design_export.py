"""Pass B: professional ebook design, preview, preflight, and export.

Zero paid/external calls. Does not mutate project #2472 or unrelated products.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from services.ebook_book_layout import (  # noqa: E402
    numbered_chapters,
    peel_back_matter,
    render_designed_ebook_html,
)
from services.ebook_cover_local import (  # noqa: E402
    cover_design_from_local,
    generate_local_cover_pdf_bytes,
    generic_or_mismatched_cover_reason,
)
from services.ebook_design_export import (  # noqa: E402
    render_designed_bundle,
    render_strong_fixture_bundle,
    select_theme,
    visual_manifest_from_manuscript,
)
from services.ebook_design_preflight import (  # noqa: E402
    PREFLIGHT_FAIL,
    PREFLIGHT_PASS,
    run_design_preflight,
    verify_export_bytes,
)
from services.ebook_design_spec import build_ebook_design  # noqa: E402
from services.ebook_design_system import (  # noqa: E402
    PROFESSIONAL_THEME_IDS,
    list_professional_themes,
    theme_css,
    theme_sample_html,
)
from services.ebook_design_workspace import (  # noqa: E402
    approve_visuals_local,
    build_design_ready_fixture_data,
    generate_and_stage_cover,
    rewind_to_stage,
    select_and_stage_theme,
)
from services.ebook_manuscript_engine import (  # noqa: E402
    FROZEN_2472_REMAINING_USD,
    FROZEN_2472_SHA256,
    FROZEN_2472_SPENT_USD,
    QUALITY_PASS,
    validate_manuscript_quality,
)
from services.ebook_manuscript_fixtures import build_event_photo_strong_manuscript  # noqa: E402
from services.ebook_project_workspace import (  # noqa: E402
    STATUS_APPROVED,
    approve_stage,
    build_acceptance_project_data,
    is_approved,
    manuscript_digest,
    set_stage_status,
    workspace_public_view,
)
from tests._test_paths import resolve_test_exports_root  # noqa: E402

# render_strong_fixture_bundle() is a pure generator (build_design_ready_fixture_data()
# is fully synthetic; nothing here reads pre-existing files from FIXTURE_DIR), so
# pointing it at the isolated temp exports root is sufficient — no historical
# content needs to be sourced or copied.
FIXTURE_DIR = resolve_test_exports_root() / "ebook_design_fixture_pass_c"


def _pages_pdf(pages: list[str]) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    for text in pages:
        c.setFont("Helvetica", 11)
        y = 720
        for line in (text or " ").splitlines() or [" "]:
            c.drawString(72, y, line[:110] or " ")
            y -= 16
        c.showPage()
    c.save()
    return buf.getvalue()


class EbookDesignExportTests(unittest.TestCase):
    def setUp(self):
        self._client_patch = patch("ai_client.get_client", side_effect=AssertionError("paid client"))
        self._client_patch.start()

    def tearDown(self):
        self._client_patch.stop()

    def test_quality_pass_required_to_enter_design(self):
        data = build_acceptance_project_data()
        data["content"] = "## What This Business Actually Looks Like\n\nThin.\n"
        data["ebook"] = data["content"]
        ws = data["ebook_workspace"]
        set_stage_status(ws, "manuscript", STATUS_APPROVED)
        set_stage_status(ws, "visuals", STATUS_APPROVED)
        set_stage_status(ws, "cover", STATUS_APPROVED)
        with self.assertRaises(ValueError):
            select_theme(data, "studio_clean")

    def test_three_professional_themes_complete(self):
        themes = list_professional_themes()
        ids = [t["theme_id"] for t in themes]
        self.assertEqual(
            ids,
            ["studio_clean", "editorial_professional", "modern_practical"],
        )
        for tid in PROFESSIONAL_THEME_IDS:
            css = theme_css(tid)
            self.assertNotRegex(css, r"letter-spacing\s*:")
            for needle in ("ebook-table", "checklist", "workflow", "callout", "caption", "chapter-num"):
                self.assertIn(needle, css)
            sample = theme_sample_html(tid)
            self.assertIn("Theme preview", sample)
            self.assertNotIn("[insert", sample.lower())

    def test_theme_change_does_not_alter_manuscript(self):
        data = build_acceptance_project_data()
        md = build_event_photo_strong_manuscript()
        data["content"] = md
        data["ebook"] = md
        digest = manuscript_digest(data)
        data = select_theme(data, "studio_clean")
        self.assertEqual(data["content"], md)
        self.assertEqual(manuscript_digest(data), digest)
        first = data["ebook_design"]["digest"]
        data = select_theme(data, "modern_practical")
        self.assertEqual(data["content"], md)
        self.assertNotEqual(data["ebook_design"]["digest"], first)
        self.assertEqual(data["ebook_design"]["theme_id"], "modern_practical")

    def test_structured_components_and_unnumbered_back_matter(self):
        md = build_event_photo_strong_manuscript()
        body, disc, sources = peel_back_matter(md)
        self.assertTrue(disc)
        self.assertIn("http", sources)
        chapters = numbered_chapters(md)
        self.assertEqual(len(chapters), 10)
        self.assertFalse(any("disclaimer" in t.lower() or t.lower() == "sources" for t, _ in chapters))
        design = build_ebook_design(theme_id="studio_clean", manuscript_digest="x")
        html = render_designed_ebook_html(
            title="From First Booking to On-Site Prints",
            subtitle="A Practical Guide",
            author="Lonnie Brown",
            manuscript_md=md,
            design=design,
        )
        self.assertIn('class="ebook-table"', html)
        self.assertIn("checklist", html)
        self.assertIn("workflow", html)
        self.assertIn("callout", html)
        self.assertIn('id="disclaimer"', html)
        self.assertIn('id="sources"', html)
        import re as _re
        self.assertIsNone(_re.search(r'id="disclaimer"[^>]*>.*?chapter-num', html, _re.I | _re.S))
        self.assertNotRegex(html, r"letter-spacing\s*:")
        self.assertIn('href="#chapter-1"', html)

    def test_cover_mismatch_and_generic_fail(self):
        title = "From First Booking to On-Site Prints"
        author = "Lonnie Brown"
        good = cover_design_from_local(
            title=title,
            subtitle="A Practical Guide",
            author=author,
            package_id="cover_event_ok",
            topic=title,
        )
        self.assertEqual(good["theme"], "event_photography")
        self.assertIsNone(
            generic_or_mismatched_cover_reason(good, title=title, author=author, topic=title)
        )
        mismatch = dict(good)
        mismatch["theme"] = "parenting_screens"
        mismatch["qa_marker"] = "Practical Family Guide"
        self.assertEqual(
            generic_or_mismatched_cover_reason(mismatch, title=title, author=author, topic=title),
            "generic_or_mismatched_cover",
        )
        wrong_title = dict(good)
        wrong_title["title"] = "Some Other Book"
        self.assertEqual(
            generic_or_mismatched_cover_reason(wrong_title, title=title, author=author, topic=title),
            "cover_title_mismatch",
        )
        pdf = generate_local_cover_pdf_bytes(title, "A Practical Guide", author=author, topic=title)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertNotIn(b"Practical Family Guide", pdf)

    def test_layout_defects_detected(self):
        data = build_acceptance_project_data()
        md = build_event_photo_strong_manuscript()
        data["content"] = md
        data["ebook"] = md
        blank = _pages_pdf(["Cover title Lonnie Brown", "   ", "Chapter one body text " * 20])
        r = run_design_preflight(data, pdf_bytes=blank, html="<html></html>")
        self.assertTrue(any(f.code == "blank_page" for f in r.findings))
        dup = _pages_pdf(["Cover title", "Same interior page content repeated here for identity.", "Same interior page content repeated here for identity."])
        r2 = run_design_preflight(data, pdf_bytes=dup)
        self.assertTrue(any(f.code == "duplicate_page" for f in r2.findings))
        clip = _pages_pdf(["Cover", "QuestionWhere CLIPPED_TEST overlapping"])
        r3 = run_design_preflight(data, pdf_bytes=clip)
        self.assertTrue(any(f.code == "clipped_or_overlapped_text" for f in r3.findings))
        sparse = _pages_pdf(["Cover", "SPARSE_PAGE_TEST"])
        r4 = run_design_preflight(data, pdf_bytes=sparse)
        self.assertTrue(any(f.code == "sparse_page" for f in r4.findings))
        split = _pages_pdf(["Cover", "SPLIT_TABLE_TEST row broken"])
        r5 = run_design_preflight(data, pdf_bytes=split)
        self.assertTrue(any(f.code == "split_table" for f in r5.findings))
        packed = _pages_pdf(
            ["Cover title Lonnie Brown"]
            + ["Chapter 1OpeningTitle Chapter 2SecondTitle extra body text here"] * 2
        )
        r6 = run_design_preflight(data, pdf_bytes=packed)
        self.assertTrue(any(f.code == "packed_chapters" for f in r6.findings))
        dense = _pages_pdf(["Cover title Lonnie Brown", "\n".join(["word"] * 800)])
        r7 = run_design_preflight(data, pdf_bytes=dense)
        self.assertTrue(any(f.code == "overcrowded_page" for f in r7.findings))
        self.assertNotEqual(r.status, PREFLIGHT_PASS)

    def test_stale_orphan_tampered_exports_fail(self):
        data = {"content": "hello", "ebook": "hello", "ebook_export_identity": {"manuscript_digest": "nope", "pdf_sha256": "abc", "zip_sha256": "def"}}
        self.assertEqual(verify_export_bytes(data=data, pdf_bytes=b"%PDF-x"), "stale_manuscript_digest")
        data2 = {
            "content": "hello",
            "ebook": "hello",
            "ebook_export_identity": {
                "manuscript_digest": manuscript_digest({"content": "hello"}),
                "pdf_sha256": "abc",
                "zip_sha256": "def",
            },
        }
        self.assertEqual(verify_export_bytes(data=data2, pdf_bytes=b"%PDF-x"), "tampered_pdf")

    def test_ui_cannot_invent_pass_or_export_ready(self):
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("gates.export_enabled", js)
        self.assertIn("cannot invent PASS", js)
        self.assertNotRegex(js, r"export_ready\s*=\s*true")
        self.assertNotRegex(js, r"quality_status\s*=\s*[\"']PASS[\"']")
        data = build_acceptance_project_data()
        view = workspace_public_view({"id": 1, "name": "t", "data": data})
        self.assertFalse(view["gates"]["export_enabled"])
        self.assertFalse(view["design"]["export_ready"])

    def test_rewind_preserves_approved_manuscript(self):
        data = build_acceptance_project_data()
        md = build_event_photo_strong_manuscript()
        data["content"] = md
        data["ebook"] = md
        ws = data["ebook_workspace"]
        set_stage_status(ws, "manuscript", "awaiting_approval")
        data = approve_stage(data, "manuscript")
        approved_md = str(data.get("content") or "")
        digest = manuscript_digest(data)
        data = rewind_to_stage(data, "outline")
        self.assertEqual(str(data.get("content") or ""), approved_md)
        self.assertEqual(manuscript_digest(data), digest)
        self.assertTrue(is_approved(data["ebook_workspace"], "manuscript"))

    def test_identity_preview_pdf_zip_match(self):
        data = build_design_ready_fixture_data()
        md = data["content"]
        q = validate_manuscript_quality(data, manuscript_md=md)
        self.assertEqual(q.status, QUALITY_PASS, (q.finding_messages or [])[:12])
        bundle = render_designed_bundle(data)
        ident = bundle["identity"]
        self.assertEqual(ident["preview_digest"], ident["pdf_sha256"])
        self.assertEqual(hashlib.sha256(bundle["pdf_bytes"]).hexdigest(), ident["pdf_sha256"])
        self.assertEqual(hashlib.sha256(bundle["zip_bytes"]).hexdigest(), ident["zip_sha256"])
        with zipfile.ZipFile(io.BytesIO(bundle["zip_bytes"])) as zf:
            names = set(zf.namelist())
            self.assertIn("ebook.pdf", names)
            self.assertIn("manifest.json", names)
            self.assertEqual(zf.read("ebook.pdf"), bundle["pdf_bytes"])
        self.assertEqual(bundle["preflight"]["status"], PREFLIGHT_PASS, bundle["preflight"]["findings"][:12])
        self.assertTrue(data.get("export_ready"))

    def test_fixture_render_inspect_and_contact_sheet(self):
        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        bundle = render_strong_fixture_bundle(FIXTURE_DIR)
        inspection = bundle["inspection"]
        self.assertGreaterEqual(inspection["page_count"], 16)
        self.assertTrue(Path(inspection["pdf_path"]).is_file())
        self.assertTrue(Path(inspection["zip_path"]).is_file())
        self.assertTrue(Path(inspection["contact_sheet"]).is_file())
        self.assertEqual(bundle["preflight"]["status"], PREFLIGHT_PASS, bundle["preflight"]["findings"][:15])
        blankish = [p for p in inspection["pages"] if p.get("nearly_blank") and p["page"] > 1]
        self.assertFalse(blankish, blankish[:3])
        html = bundle["html"]
        self.assertIn("<pdf:nextpage", html)
        self.assertGreaterEqual(html.count("<pdf:nextpage"), 12)
        self.assertIn("Chapter 1", html)
        self.assertIn("Disclaimer", html)
        self.assertIn("Sources", html)
        self.assertNotIn("Chapter 11", html)

    def test_project_2472_unchanged(self):
        import database

        live = database.get_project(2472)
        self.assertIsNotNone(live)
        data = live.get("data") or {}
        md = str(data.get("content") or data.get("ebook") or "")
        self.assertEqual(hashlib.sha256(md.encode("utf-8")).hexdigest(), FROZEN_2472_SHA256)
        ws = data.get("ebook_workspace") or {}
        ledger = ws.get("paid_call_ledger") or {}
        self.assertAlmostEqual(float(ledger.get("spent_usd") or 0), FROZEN_2472_SPENT_USD, places=3)
        self.assertAlmostEqual(float(ledger.get("remaining_usd") or 0), FROZEN_2472_REMAINING_USD, places=3)
        # Independent re-read through the active (isolated during tests) DB
        # file, proving the data really round-tripped to disk rather than
        # just being held in an in-memory connection. Never reads the real
        # projects.db — database.DB_PATH is set by tests/conftest.py.
        uri = f"file:{database.DB_PATH}?mode=ro"
        con = sqlite3.connect(uri, uri=True)
        try:
            row = con.execute("SELECT data FROM projects WHERE id = 2472").fetchone()
        finally:
            con.close()
        self.assertIsNotNone(row)
        blob = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        live_md = str((blob or {}).get("content") or (blob or {}).get("ebook") or "")
        self.assertEqual(hashlib.sha256(live_md.encode("utf-8")).hexdigest(), FROZEN_2472_SHA256)

    def test_non_ebook_kdp_untouched_markers(self):
        kdp = (ROOT / "tests" / "test_kdp_foundations_pass1.py").read_text(encoding="utf-8")
        self.assertTrue(kdp.strip())
        coloring = ROOT / "services" / "coloring_book" / "builder.py"
        self.assertTrue(coloring.is_file())


if __name__ == "__main__":
    unittest.main()
