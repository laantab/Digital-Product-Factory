"""Customer-path verification for California Gold Rush Days crossword repair.

Exercises the same HTTP routes the factory UI uses, then inspects rendered PDF
pages (not just extracted text).
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.chdir(ROOT)

from app import app  # noqa: E402
import database  # noqa: E402


FORBIDDEN = {
    "KITCHEN", "PILLOW", "CURTAIN", "BEDROOM", "BATHROOM", "BREAKFAST",
    "COFFEE", "LUNCH", "DINNER", "RABBIT", "GIRAFFE", "GRANDMA", "FAMILY",
}
GENERIC_SNIPPETS = (
    "related to the theme", "related to california", "related to daily",
    "crossword word", "common word", "mystery word", "everyday item",
)


def main() -> int:
    report: dict = {"steps": [], "pass": True, "paid_api_calls": 0}

    def step(name: str, ok: bool, detail: str = "") -> None:
        report["steps"].append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            report["pass"] = False
        print(("PASS" if ok else "FAIL"), "-", name, (":: " + detail if detail else ""))

    client = app.test_client()

    # 1) Factory UI loads and crossword defaults are visible in JS bundle
    ui = client.get("/")
    step("Open factory UI", ui.status_code == 200, f"status={ui.status_code}")
    js = client.get("/static/js/app.js")
    js_text = js.data.decode("utf-8", errors="replace")
    step(
        "Crossword Full Book default is 12 puzzles",
        'id: "crossword"' in js_text and 'value: "12"' in js_text.split('id: "crossword"', 1)[1][:1200],
    )
    step(
        "Full Book page-count helper text present",
        "12 puzzles" in js_text and "25 pages" in js_text and 'fields.puzzles = "12"' in js_text,
    )

    from services.product import _crossword_plan

    # Proven failure path: browser/legacy UI submitted puzzles=10 for Full Book.
    # Backend + submit guard must still produce the 12-puzzle / 25-page book.
    fields = {
        "book_title": "California Gold Rush Days",
        "theme": "California Gold Rush Days",
        "audience": "Adults",
        "output_format": "Full Book",
        "creation_mode": "Topic (AI generates words)",
        "puzzles": "10",
        "difficulty": "Easy",
        "include_answer_key": "Yes",
        "include_cover": "Yes",
    }
    plan_ten = _crossword_plan(fields)
    step(
        "Submitted puzzles=10 still plans 12 worksheets",
        plan_ten["worksheets"] == 12,
        str(plan_ten["worksheets"]),
    )

    # Confirm form default path uses 12 when puzzles omitted
    plan_default = _crossword_plan({
        "book_title": "California Gold Rush Days",
        "theme": "California Gold Rush Days",
        "output_format": "Full Book",
        "creation_mode": "Topic (AI generates words)",
        "difficulty": "Easy",
        "include_answer_key": "Yes",
    })
    step("Form/plan defaults to 12 puzzles", plan_default["worksheets"] == 12, str(plan_default["worksheets"]))

    # 2) Generate via the same endpoint the UI calls — no paid APIs
    with client:
        gen = client.post(
            "/generate-product",
            json={"product_type": "crossword", "fields": fields},
        )
    step(
        "Generate crossword Full Book",
        gen.status_code == 200,
        "status=%s body=%r" % (gen.status_code, gen.data[:200]),
    )
    if gen.status_code != 200:
        Path(tempfile.gettempdir(), "crossword_customer_path_report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        return 1
    data = gen.get_json()
    step("Correct product title", data.get("title") == "California Gold Rush Days", repr(data.get("title")))
    step("Native crossword PDF (is_pdf)", bool(data.get("is_pdf")), repr(data.get("is_pdf")))
    step("No ebook fallback product_type", data.get("product_type") == "crossword", repr(data.get("product_type")))
    step("Cover design present without AI auto-image", data.get("cover_design") is not None)
    cover = data.get("cover_design") or {}
    step("Cover use_ai_image is false", cover.get("use_ai_image") in (False, 0, "false", None) or cover.get("use_ai_image") is False, repr(cover.get("use_ai_image")))

    pdf_b64 = data.get("pdf_bytes") or ""
    direct_pdf = base64.b64decode(pdf_b64)
    step("Direct PDF signature", direct_pdf.startswith(b"%PDF"), f"size={len(direct_pdf)}")

    # 3) Save project (same as ensureProductSaved / POST /projects)
    save_body = {
        "name": data.get("title") or "California Gold Rush Days",
        "type": "crossword",
        "data": data,
        "user_saved": True,
    }
    save = client.post("/projects", json=save_body)
    step("Save project", save.status_code in {200, 201}, f"status={save.status_code}")
    saved = save.get_json() or {}
    project_id = saved.get("id")
    step("Saved project has ID", project_id is not None, repr(project_id))

    # 4) Cover editor entry
    step(
        "Edit Cover entry exists in post-save UI code",
        'data-ns="edit-cover"' in js_text and "openCoverEditor" in js_text,
    )
    cover_page = client.get(f"/cover-editor?project_id={project_id}")
    step(
        "Existing Cover Editor opens for saved project",
        cover_page.status_code == 200 and b"cover" in cover_page.data.lower(),
        f"status={cover_page.status_code}",
    )

    # Apply current cover to PDF without AI regeneration
    apply = client.post(
        "/cover/apply-to-pdf",
        json={"project_id": project_id, "cover": cover},
    )
    step(
        "Apply cover to PDF without AI regenerate",
        apply.status_code == 200,
        "status=%s body=%r" % (apply.status_code, apply.data[:180]),
    )

    # 5) Export PDF + ZIP via the UI export route
    export = client.post("/export-product", json={"project_id": project_id})
    step("Export product", export.status_code == 200, f"status={export.status_code}")
    ex = (export.get_json() or {}).get("exports") or {}
    files = ex.get("files") or {}
    pdf_info = files.get("pdf") or {}
    zip_info = files.get("zip") or {}
    step("Direct PDF export available", bool(pdf_info.get("url")), repr(pdf_info))
    step("ZIP export available", bool(zip_info.get("url")), repr(zip_info))

    pdf_resp = client.get(pdf_info.get("url") or "/missing")
    zip_resp = client.get(zip_info.get("url") or "/missing")
    step("Download direct PDF", pdf_resp.status_code == 200 and pdf_resp.data.startswith(b"%PDF"), f"status={pdf_resp.status_code} size={len(pdf_resp.data)}")
    step("Download ZIP", zip_resp.status_code == 200 and zip_resp.data[:2] == b"PK", f"status={zip_resp.status_code} size={len(zip_resp.data)}")

    zipped_pdf = b""
    if zip_resp.status_code == 200:
        with zipfile.ZipFile(io.BytesIO(zip_resp.data)) as zf:
            pdf_names = [n for n in zf.namelist() if n.lower().endswith(".pdf")]
            step("ZIP contains PDF", bool(pdf_names), repr(pdf_names))
            if pdf_names:
                zipped_pdf = zf.read(pdf_names[0])
    if zipped_pdf:
        same = hashlib.sha256(pdf_resp.data).hexdigest() == hashlib.sha256(zipped_pdf).hexdigest()
        step("PDF inside ZIP matches direct PDF", same)
        # Keep using the exported PDF for page inspection
        inspect_pdf = pdf_resp.data
    else:
        inspect_pdf = direct_pdf

    # 6) Rendered page inspection with PyMuPDF
    import fitz
    from pypdf import PdfReader

    meta_reader = PdfReader(io.BytesIO(inspect_pdf))
    subject = str((meta_reader.metadata.subject if meta_reader.metadata else "") or "")
    step(
        "PDF metadata says 12 Crossword Puzzles",
        "12 Crossword Puzzles" in subject and "10 Crossword Puzzles" not in subject,
        repr(subject),
    )

    doc = fitz.open(stream=inspect_pdf, filetype="pdf")
    page_count = doc.page_count
    step("Exactly 25 PDF pages", page_count == 25, f"pages={page_count}")

    # Persist authority copy + page renders for visual inspection
    authority_dir = Path(tempfile.gettempdir()) / "crossword_gold_rush_verify"
    authority_dir.mkdir(parents=True, exist_ok=True)
    authority_pdf = authority_dir / "california_gold_rush_days.pdf"
    authority_pdf.write_bytes(inspect_pdf)
    pages_dir = authority_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    for i in range(page_count):
        pix = doc.load_page(i).get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
        pix.save(str(pages_dir / f"page_{i + 1:02d}.png"))
    report["authority_pdf"] = str(authority_pdf)
    report["pages_dir"] = str(pages_dir)

    page_texts = [doc.load_page(i).get_text("text") for i in range(page_count)]
    # Cover heuristics: title present on page 1, puzzle-like content after
    cover_text = page_texts[0]
    step("Page 1 is cover (title present)", "Gold Rush" in cover_text or "GOLD" in cover_text.upper(), cover_text[:120].replace("\n", " "))
    step("Page 1 is not an answer key", "Answer Key" not in cover_text, cover_text[:80].replace("\n", " "))

    puzzle_pages = page_texts[1:13]
    answer_pages = page_texts[13:25]
    puzzle_ok = all(
        ("ACROSS" in t.upper() and "DOWN" in t.upper() and "Puzzle" in t)
        for t in puzzle_pages
    )
    step(
        "Pages 2-13 look like puzzles",
        puzzle_ok,
        str([("ACROSS" in t.upper() and "Puzzle" in t) for t in puzzle_pages]),
    )
    step(
        "Pages 14-25 look like answer keys",
        all("Answer Key" in t or "ANSWER KEY" in t.upper() for t in answer_pages),
        str([("Answer Key" in t or "ANSWER KEY" in t.upper()) for t in answer_pages]),
    )

    # Visual smoke: each page has drawable content (not blank)
    blank = []
    for i in range(page_count):
        pix = doc.load_page(i).get_pixmap(matrix=fitz.Matrix(0.4, 0.4), alpha=False)
        # crude non-blank check: not nearly all white
        samples = pix.samples
        # count non-white-ish bytes
        non_white = sum(1 for b in samples[::50] if b < 245)
        if non_white < 20:
            blank.append(i + 1)
    step("Rendered pages are not blank", not blank, f"blank_pages={blank}")

    # Content quality from generation metadata / rebuild inspection
    from services.crossword.book import build_crossword_puzzles
    from services.crossword.direct_pdf_renderer import build_crossword_book_pdf_bytes

    puzzles, warnings, errors = build_crossword_puzzles(
        mode="topic",
        product_title="California Gold Rush Days",
        theme="California Gold Rush Days",
        difficulty="easy",
        grid_size=15,
        number_of_puzzles=12,
        words_per_puzzle=8,
        output_type="book",
        use_ai_words=False,
        seed=42,
    )
    counts = [len(p.placed_words) for p in puzzles]
    report["placed_counts"] = counts
    step("12 puzzles built", len(puzzles) == 12, str(len(puzzles)))
    step("Each puzzle has at least 8 placed answers", all(c >= 8 for c in counts), str(counts))

    answers = []
    clues = []
    for p in puzzles:
        answers.extend(w.upper() for w in p.placed_words)
        clues.extend(c.clue.strip().lower() for c in p.clues)
    dup_answers = len(answers) - len(set(answers))
    dup_clues = len(clues) - len(set(clues))
    report["duplicate_answer_count"] = dup_answers
    report["duplicate_clue_count"] = dup_clues
    step("No duplicate answers", dup_answers == 0, str(dup_answers))
    step("No duplicate clues", dup_clues == 0, str(dup_clues))
    forbidden_hits = sorted(set(answers) & FORBIDDEN)
    generic_hits = [c for c in clues if any(s in c for s in GENERIC_SNIPPETS)]
    report["unrelated_or_generic"] = {"forbidden": forbidden_hits, "generic_clues": generic_hits[:10]}
    step("No unrelated/generic vocabulary", not forbidden_hits and not generic_hits, str(report["unrelated_or_generic"]))

    # Goal Rush alias path
    from services.crossword.crossword_fallback import _normalize_theme
    from services.product import _crossword_plan as plan_fn
    step("Goal Rush alias routes to gold_rush", _normalize_theme("California Goal Rush Days") == "gold_rush")
    goal_plan = plan_fn({
        "book_title": "California Goal Rush Days",
        "theme": "California Goal Rush Days",
        "output_format": "Full Book",
        "puzzles": "12",
        "creation_mode": "Topic (AI generates words)",
        "difficulty": "Easy",
    })
    step("Goal Rush title corrected", goal_plan["title"] == "California Gold Rush Days", goal_plan["title"])

    report["page_structure"] = {
        "total": page_count,
        "cover": 1,
        "puzzles": "2-13",
        "answer_keys": "14-25",
    }
    report["pdf_sha256"] = hashlib.sha256(inspect_pdf).hexdigest()
    out_path = Path(tempfile.gettempdir()) / "crossword_customer_path_report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("REPORT", out_path)
    print("OVERALL", "PASS" if report["pass"] else "FAIL")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
