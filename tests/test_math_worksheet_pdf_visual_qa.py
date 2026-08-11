"""Regression: Math Worksheet PDF visual QA defects.

Locks:
1. No duplicated Grade label
2. Instruction rendered once (no overlap/duplication)
3. Selected operation matches every problem
4. Correct two-page numbering when answer key included
5. Answer-key layout stays inside safe margins
6. Extracted PDF text contains expected labels/problems
7. Rendered pages pass measurable layout checks
8. Final Output PDF/ZIP download links still work
"""
from __future__ import annotations

import os
import random
import re
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("FACTORY_TEST_MODE", "1")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("TAVILY_API_KEY", "")
os.environ.setdefault("AI_INTEGRATIONS_OPENAI_API_KEY", "")

from services.math_worksheet.builder import build_math_worksheet
from services.math_worksheet.pdf_builder import MathWorksheetPdfRequest, build_math_worksheet_pdf
from services.math_worksheet.pdf_fonts import MATH_FONT, MATH_FONT_BOLD, ensure_math_fonts

ROOT = Path(__file__).resolve().parents[1]
_EXPORT_DIR = ROOT / "exports" / "math_worksheet_visual_qa_fixture"
_MARGIN = 0.5 * 72.0
_PAGE_W, _PAGE_H = 612.0, 792.0


def _deterministic_pdf(*, topic: str = "Multiplication", grade: str = "Grade 6", seed: int = 42):
    random.seed(seed)
    req = MathWorksheetPdfRequest(
        worksheet_title="Grade 6 Multiplication Practice",
        grade=grade,
        math_topic=topic,
        difficulty="Medium",
        problem_count=20,
        include_answer_key=True,
        include_challenge=False,
        package_id="math_worksheet_visual_qa_fixture",
        seed=seed,
    )
    result = build_math_worksheet_pdf(req)
    assert not result.errors, result.errors
    assert result.pdf_bytes.startswith(b"%PDF")
    return result


class MathWorksheetPdfVisualQaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_math_fonts()
        cls.result = _deterministic_pdf()
        cls.pdf_bytes = cls.result.pdf_bytes
        _EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        ( _EXPORT_DIR / "worksheet.pdf").write_bytes(cls.pdf_bytes)

    def _doc(self):
        import fitz
        return fitz.open(stream=self.pdf_bytes, filetype="pdf")

    def test_no_duplicated_grade_label(self):
        doc = self._doc()
        blob = "\n".join(doc.load_page(i).get_text("text") for i in range(doc.page_count))
        self.assertNotIn("Grade Grade", blob)
        self.assertRegex(blob, r"\bGrade 6\b")
        # Meta line should contain exactly one Grade token near Multiplication.
        page0 = doc.load_page(0).get_text("text")
        self.assertEqual(len(re.findall(r"\bGrade\b", page0.splitlines()[1] if len(page0.splitlines()) > 1 else page0)), 1)

    def test_instruction_rendered_once_no_overlap(self):
        import fitz
        doc = self._doc()
        page = doc.load_page(0)
        instruction = "Solve each problem. Show your work. Write your final answer in the answer blank."
        spans = []
        for block in page.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = (span.get("text") or "").strip()
                    if "Solve each problem" in text:
                        spans.append(span)
        self.assertEqual(len(spans), 1, f"Expected one instruction span, got {len(spans)}")
        # No near-duplicate instruction y baselines (overlap / double-draw).
        words = [w for w in page.get_text("words") if w[4] == "Solve"]
        self.assertEqual(len(words), 1)
        # Instruction must not intersect problem #1 text bbox.
        instr_bbox = fitz.Rect(spans[0]["bbox"])
        found_problem = False
        for w in page.get_text("words"):
            if w[4] == "1.":
                pbox = fitz.Rect(w[:4])
                self.assertFalse(instr_bbox.intersects(pbox), "Instruction overlaps problem number")
                found_problem = True
                break
        self.assertTrue(found_problem, "Problem 1. not found on worksheet page")
        self.assertIn(instruction, page.get_text("text"))

    def test_selected_operation_matches_every_problem(self):
        # Builder contract
        random.seed(7)
        ws = build_math_worksheet(
            worksheet_title="Mul Only",
            grade="Grade 6",
            math_topic="Multiplication",
            difficulty="Medium",
            problem_count=20,
            include_answer_key=True,
        )
        self.assertEqual(ws.math_topic, "Multiplication")
        for p in ws.problems:
            self.assertIn(" x ", p.expression, p.expression)
            self.assertNotIn("+", p.expression.replace("x", ""))
            self.assertTrue(re.search(r"\d+\s+x\s+\d+\s*=\s*\?", p.expression), p.expression)

        # PDF text contract
        doc = self._doc()
        page0 = doc.load_page(0).get_text("text")
        self.assertIn("Multiplication", page0)
        # Every numbered problem line should be multiplication.
        mul_lines = re.findall(r"^\s*\d+\.\s*.*$", page0, flags=re.M)
        self.assertGreaterEqual(len(mul_lines), 10)
        for line in mul_lines:
            self.assertRegex(line, r"\d+\s+x\s+\d+\s*=\s*\?")
            self.assertNotRegex(line, r"\d+\s+[+\-/]\s+\d+")

    def test_mixed_operations_label_when_mixed_intended(self):
        random.seed(9)
        ws = build_math_worksheet(
            worksheet_title="Mixed Practice",
            grade="Grade 4",
            math_topic="Mixed Arithmetic",
            difficulty="Easy",
            problem_count=12,
        )
        self.assertEqual(ws.math_topic, "Mixed Operations")
        ops = []
        for p in ws.problems:
            if " x " in p.expression:
                ops.append("*")
            elif " / " in p.expression:
                ops.append("/")
            elif " + " in p.expression:
                ops.append("+")
            elif " - " in p.expression:
                ops.append("-")
        self.assertGreaterEqual(len(set(ops)), 2)

    def test_correct_two_page_numbering(self):
        import fitz
        doc = self._doc()
        self.assertEqual(doc.page_count, 2)
        p1 = doc.load_page(0).get_text("text")
        p2 = doc.load_page(1).get_text("text")
        self.assertIn("Page 1 of 2", p1)
        self.assertIn("Page 2 of 2", p2)
        self.assertNotIn("Page 1 of 1", p1)
        self.assertNotIn("Page 1 of 1", p2)
        self.assertIn("Answer Key", p2)

    def test_answer_key_layout_inside_safe_margins(self):
        import fitz
        doc = self._doc()
        page = doc.load_page(1)
        words = page.get_text("words")
        self.assertTrue(words)
        for w in words:
            x0, y0, x1, y1, text = w[:5]
            self.assertGreaterEqual(x0, _MARGIN - 1.0, text)
            self.assertLessEqual(x1, _PAGE_W - _MARGIN + 1.0, text)
            self.assertGreaterEqual(y0, _MARGIN - 8.0, text)
            self.assertLessEqual(y1, _PAGE_H - _MARGIN + 8.0, text)

        # Two clearly separated column Answer headers (exclude title "Answer Key").
        problem_headers = [w for w in words if w[4] == "Problem"]
        self.assertGreaterEqual(len(problem_headers), 2)
        header_ys = {round(w[1], 1) for w in problem_headers}
        # Prefer the shared column-header baseline.
        header_y = sorted(header_ys)[0]
        answer_headers = [
            w for w in words
            if w[4] == "Answer" and abs(w[1] - header_y) < 2.0
        ]
        self.assertGreaterEqual(len(answer_headers), 2)
        xs = sorted(w[0] for w in answer_headers)
        self.assertGreater(xs[1] - xs[0], 180, "Answer columns are not clearly separated")

    def test_extracted_pdf_text_contains_expected_labels_and_problems(self):
        doc = self._doc()
        blob = "\n".join(doc.load_page(i).get_text("text") for i in range(doc.page_count))
        self.assertIn("Grade 6 Multiplication Practice", blob)
        self.assertIn("Multiplication", blob)
        self.assertIn("Medium", blob)
        self.assertIn("Answer Key", blob)
        self.assertIn("Solve each problem", blob)
        # Problems + answers from fixture payload remain present and correct.
        for problem in self.result.problems[:5]:
            self.assertIn(problem["expression"].replace("×", "x").replace("÷", "/"), blob)
            self.assertIn(str(problem["answer"]), blob)

    def test_rendered_pages_pass_layout_checks(self):
        import fitz
        from PIL import Image

        doc = self._doc()
        fonts = set()
        for i in range(doc.page_count):
            page = doc.load_page(i)
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            img_path = _EXPORT_DIR / f"page_{i + 1}.png"
            pix.save(str(img_path))
            img = Image.open(img_path)
            self.assertEqual(img.mode, "RGB")
            self.assertGreater(img.size[0], 700)
            self.assertGreater(img.size[1], 900)
            # Mostly white printable page (ink should not flood).
            # Sample center band mean lightness.
            sample = img.crop((40, 40, img.size[0] - 40, img.size[1] - 40))
            hist = sample.convert("L").histogram()
            total = sum(hist) or 1
            bright = sum(hist[200:]) / total
            self.assertGreater(bright, 0.70, f"Page {i+1} too dark for print worksheet")

            for block in page.get_text("dict").get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        fonts.add(span.get("font") or "")
                        text = span.get("text") or ""
                        # Reject artificially spaced title forms.
                        self.assertIsNone(
                            re.search(r"G\s+r\s+a\s+d\s+e", text),
                            text,
                        )

        joined = " ".join(fonts).lower()
        self.assertTrue(
            MATH_FONT.lower() in joined
            or "arial" in joined
            or MATH_FONT_BOLD.lower() in joined,
            f"Expected embedded math fonts, found {fonts}",
        )

    def test_answers_remain_mathematically_correct(self):
        for p in self.result.problems:
            expr = p["expression"]
            m = re.match(r"^\s*(\d+)\s*([+\-x/])\s*(\d+)\s*=\s*\?\s*$", expr)
            self.assertIsNotNone(m, expr)
            a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
            if op == "+":
                expected = a + b
            elif op == "-":
                expected = a - b
            elif op == "x":
                expected = a * b
            else:
                expected = a // b
            self.assertEqual(str(expected), str(p["answer"]), expr)

    def test_final_output_pdf_zip_links_still_work(self):
        from app import app
        from services.math_worksheet import pdf_builder as mw

        client = app.test_client()
        fields = {
            "worksheet_title": "Math Visual QA Link Check",
            "grade": "Grade 6",
            "math_topic": "Multiplication",
            "difficulty": "Medium",
            "problems": "8",
            "include_answer_key": "Yes",
            "include_challenge": "No",
            # Book output keeps the answer-key page (single-worksheet auto-strips it).
            "output_format": "Book",
            "audience": "Grade 6 students",
            "goal": "Practice multiplication",
        }
        with patch.object(mw, "build_math_worksheet_pdf", wraps=mw.build_math_worksheet_pdf):
            prev = client.post(
                "/generate-product",
                json={"product_type": "math_worksheet", "fields": fields},
            )
        self.assertEqual(prev.status_code, 200, prev.data)
        preview = prev.get_json()
        save = client.post(
            "/projects",
            json={
                "name": preview.get("title") or "Math Visual QA Link Check",
                "type": "product",
                "user_saved": True,
                "system_test": True,
                "temporary": True,
                "data": {k: v for k, v in preview.items() if not str(k).startswith("_")},
            },
        )
        self.assertEqual(save.status_code, 201, save.data)
        pid = save.get_json()["id"]
        try:
            ex = client.post("/export-product", json={"project_id": pid})
            self.assertEqual(ex.status_code, 200, ex.data)
            files = (ex.get_json().get("exports") or {}).get("files") or {}
            self.assertIn("pdf", files)
            self.assertIn("zip", files)
            pdf_dl = client.get(files["pdf"]["url"])
            zip_dl = client.get(files["zip"]["url"])
            self.assertEqual(pdf_dl.status_code, 200)
            self.assertEqual(zip_dl.status_code, 200)
            self.assertTrue(pdf_dl.data.startswith(b"%PDF"))
            self.assertTrue(zip_dl.data.startswith(b"PK"))
            # Customer PDF must also carry the fixed page labels.
            import fitz
            doc = fitz.open(stream=pdf_dl.data, filetype="pdf")
            self.assertEqual(doc.page_count, 2)
            self.assertIn("Page 1 of 2", doc.load_page(0).get_text("text"))
            self.assertIn("Page 2 of 2", doc.load_page(1).get_text("text"))
        finally:
            client.delete(f"/projects/{pid}")


if __name__ == "__main__":
    unittest.main()
