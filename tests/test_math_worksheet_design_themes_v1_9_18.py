"""Customer path and measured PDF checks for selectable Math Worksheet themes."""
from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("FACTORY_TEST_MODE", "1")
os.environ.setdefault("OPENAI_API_KEY", "")


class MathWorksheetDesignThemeTests(unittest.TestCase):
    def test_themes_change_printed_design_without_changing_content_or_geometry(self):
        import fitz

        from services.math_worksheet.builder import build_math_worksheet
        from services.math_worksheet.renderer import build_math_worksheet_pdf_bytes
        from services.math_worksheet.themes import resolve_math_worksheet_theme

        # Classic uses the legacy ink tokens; a missing/old selection must not
        # darken or otherwise restyle an existing worksheet.
        self.assertEqual(resolve_math_worksheet_theme(None).ink, "#374151")

        worksheet = build_math_worksheet(
            worksheet_title="Grade 4 Addition Practice",
            grade="4",
            math_topic="Addition",
            difficulty="Medium",
            problem_count=20,
            include_answer_key=True,
            include_challenge=False,
        )
        self.assertFalse(worksheet.errors, worksheet.errors)
        outputs = {}
        for theme in ("classic_classroom", "calm_focus", "bright_practice"):
            pdf_bytes, layout = build_math_worksheet_pdf_bytes(
                worksheet, include_answer_key=True, include_cover=True,
                design_theme=theme,
            )
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            text = [page.get_text("text") for page in doc]
            fonts = {
                span["font"]
                for page in doc
                for block in page.get_text("dict")["blocks"]
                if "lines" in block
                for line in block["lines"]
                for span in line["spans"]
            }
            raster = doc[1].get_pixmap(matrix=fitz.Matrix(0.75, 0.75), alpha=False).samples
            outputs[theme] = (doc.page_count, tuple(round(x) for x in doc[0].rect), text, fonts, raster, layout)

        baseline = outputs["classic_classroom"]
        self.assertIn("20.", baseline[2][1], "the worksheet omitted a problem at the highest per-page count")
        for theme in ("calm_focus", "bright_practice"):
            current = outputs[theme]
            self.assertEqual(current[0], baseline[0], "theme changed page count")
            self.assertEqual(current[1], baseline[1], "theme changed page dimensions")
            self.assertEqual(current[2], baseline[2], "theme changed problem or answer text")
            self.assertNotEqual(current[4], baseline[4], f"{theme} rendered identically to Classic")
            self.assertEqual(current[5].worksheet_pages, baseline[5].worksheet_pages)
            self.assertEqual(current[5].answer_key_pages, baseline[5].answer_key_pages)
        self.assertTrue(any("Serif" in name for name in outputs["bright_practice"][3]))
        self.assertTrue(any("Sans" in name for name in outputs["classic_classroom"][3]))

    def test_selected_theme_survives_generate_save_reopen_and_export(self):
        import base64
        from zipfile import ZipFile
        from io import BytesIO
        import fitz

        from app import app

        client = app.test_client()
        fields = {
            "worksheet_title": "TEST Grade 4 Theme Round Trip",
            "grade": "Grade 4",
            "math_topic": "Addition",
            "difficulty": "Easy",
            "problems": "8",
            "include_answer_key": "Yes",
            "include_challenge": "No",
            "include_cover": "No",
            "design_theme": "bright_practice",
        }
        generated = client.post(
            "/generate-product",
            json={"product_type": "math_worksheet", "fields": fields},
        )
        self.assertEqual(generated.status_code, 200, generated.data)
        preview = generated.get_json()
        self.assertEqual(preview["fields"]["design_theme"], "bright_practice")
        pdf = base64.b64decode(preview["pdf_bytes"])
        from tests._test_paths import resolve_test_exports_root
        saved_pdf = resolve_test_exports_root() / preview["package_id"] / preview["filename"]
        self.assertTrue(saved_pdf.is_file())
        saved_doc = fitz.open(saved_pdf)
        preview_doc = fitz.open(stream=pdf, filetype="pdf")
        self.assertEqual(saved_doc.page_count, preview_doc.page_count)
        self.assertEqual(
            [p.get_text("text") for p in saved_doc],
            [p.get_text("text") for p in preview_doc],
        )
        self.assertEqual(saved_doc[0].rect, preview_doc[0].rect)
        self.assertTrue(any("Serif" in f[3] for f in saved_doc[0].get_fonts(full=True)))

        saved = client.post(
            "/projects",
            json={
                "name": fields["worksheet_title"],
                "type": "product",
                "user_saved": True,
                "system_test": True,
                "temporary": True,
                "data": {k: v for k, v in preview.items() if not str(k).startswith("_")},
            },
        )
        self.assertEqual(saved.status_code, 201, saved.data)
        project_id = saved.get_json()["id"]
        try:
            reopened = client.get(f"/projects/{project_id}")
            self.assertEqual(reopened.status_code, 200, reopened.data)
            reopened_data = reopened.get_json()["data"]
            self.assertEqual(reopened_data["fields"]["design_theme"], "bright_practice")

            exported = client.post("/export-product", json={"project_id": project_id})
            self.assertEqual(exported.status_code, 200, exported.data)
            files = exported.get_json()["exports"]["files"]
            pdf_response = client.get(files["pdf"]["url"])
            zip_response = client.get(files["zip"]["url"])
            self.assertEqual(pdf_response.status_code, 200)
            self.assertEqual(zip_response.status_code, 200)
            self.assertEqual(pdf_response.data, pdf)
            with ZipFile(BytesIO(zip_response.data)) as archive:
                bundled_pdf = next(n for n in archive.namelist() if n.endswith(".pdf"))
                self.assertEqual(archive.read(bundled_pdf), pdf_response.data)
            doc = fitz.open(stream=pdf_response.data, filetype="pdf")
            self.assertTrue(any("Serif" in f[3] for f in doc[0].get_fonts(full=True)))
        finally:
            client.delete(f"/projects/{project_id}")

    def test_form_exposes_a_safe_default_and_all_three_choices(self):
        source = (Path(__file__).resolve().parents[1] / "static/js/app.js").read_text(encoding="utf-8")
        start = source.index('id: "math_worksheet"')
        end = source.index('id: "spelling_worksheet"', start)
        block = source[start:end]
        self.assertIn('name: "design_theme"', block)
        self.assertIn('default: "classic_classroom"', block)
        for key in ("classic_classroom", "calm_focus", "bright_practice"):
            self.assertIn(f'value: "{key}"', block)


if __name__ == "__main__":
    unittest.main()
