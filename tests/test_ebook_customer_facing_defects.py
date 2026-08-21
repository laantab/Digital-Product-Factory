"""Regression for customer-facing ebook defects: tables, leakage, front matter, TOC, sources.

Zero paid/external calls. Isolated projects except read-only #4249 identity checks.
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import database  # noqa: E402
from services.ebook_customer_facing import (  # noqa: E402
    CONCATENATED_HEADER_SAMPLES,
    MARGIN_RECALCULATIONS,
    detect_customer_facing_defects,
    inspect_customer_facing_output,
    inspect_html_tables,
    inspect_rendered_ebook,
    polish_heading,
    sanitize_customer_manuscript,
    unescape_source_url,
)
from services.ebook_book_layout import render_designed_ebook_html  # noqa: E402
from services.ebook_design_preflight import run_design_preflight  # noqa: E402
from services.ebook_design_spec import build_ebook_design  # noqa: E402
from services.ebook_project_workspace import build_acceptance_project_data  # noqa: E402

LIVE_4249 = 4249
EXPECTED_COVER_SHA = "465a3e10861cd056a98008a8131be157be9dc0d22ec93464fa831fcbb03367cd"
EXPECTED_COVER_DIGEST = "55567b21e03e3d5734ff5c355c3f4771b4771480d88566ebbdabcbd0d970d016"

WIDE_TABLE_MD = """## Chapter 1

| Event niche | Typical client need | Guest interaction level | Planning complexity | Sales opportunity | Main beginner caution |
|---|---|---|---|---|---|
| Weddings | Timeline coverage | Medium | High | Moderate | Backup gear |
| Parties | Candid fun | High | Low | Strong | Lighting |
"""

FOUR_COL_MD = """## Chapter 1

| Stage | When | What to confirm | Why it matters |
|---|---|---|---|
| Inquiry | Week 1 | Date and venue | Locks the calendar |
| Contract | Week 2 | Deliverables | Prevents scope drift |
"""

FIVE_COL_MD = """## Chapter 1

| Startup lane | Typical planning range | What it usually includes | Legal/insurance priority | Launch risk if skipped |
|---|---|---|---|---|
| Lean start | $2,000 to $5,000 | One body and a kit lens | General liability | Uninsurable jobs |
"""

SEVEN_COL_MD = """## Chapter 1

| Kit level | Camera bodies | Lenses | Lighting | Computing/editing | Printing equipment | Best use |
|---|---|---|---|---|---|---|
| Starter | One body | One zoom | On-camera flash | Laptop | None | First bookings |
"""

LONG_HEADER_SIX_MD = """## Chapter 1

| Event niche | Typical client need | Guest interaction level | Planning complexity | Sales opportunity for on-site prints | Main beginner caution |
|---|---|---|---|---|---|
| Weddings | Timeline coverage | Medium | High | Moderate | Backup gear |
"""

LONG_TIMELINE_MD = """## Chapter 1

| Stage | When | What to confirm | Why it matters |
|---|---|---|---|
| Initial inquiry | At first contact | Event type, date, venue, hours needed, whether printing is requested | Filters out poor-fit jobs early |
| Booking | At contract signing | Coverage hours, payment schedule, access times, client contact person | Creates clear responsibility |
| Early planning | 3-4 weeks before | Shot priorities, venue rules, floor layout, print station request, staffing plan | Prevents surprise restrictions |
| Final confirmation | 7-10 days before | Final timeline, power access, load-in route, table/chair needs, weather backup if relevant | Locks down logistics |
| Pre-event check | 24-48 hours before | Arrival time, emergency contact, ceremony or program changes, vendor coordination | Catches last-minute changes |
| Arrival and setup | Event day, before guests | Space layout, cable paths, power test, staff assignments, print workflow | Reduces opening chaos |
| During event | Event live | Schedule updates, line management, print expectations, break coverage | Keeps service consistent |
| Breakdown | End of event | Media packing, file handling, client sign-off if needed, leftover-print plan | Protects files and close-out |
"""

TIMELINE_STAGES = (
    "Initial inquiry",
    "Booking",
    "Early planning",
    "Final confirmation",
    "Pre-event check",
    "Arrival and setup",
    "During event",
    "Breakdown",
)

LEAKY_MD = """## Finding Clients

### MANDATORY DELIVERABLE [inquiry-to-booking scenario]

**Hypothetical / planning example: inquiry-to-booking scenario**

Ask for the date first.

### MANDATORY DELIVERABLE [hypothetical dollar-margin scenario]

The example below is a hypothetical planning worksheet.

### Checklist: insurance-and-coi

- [ ] General liability
- [ ] Reserved at least $2.50 for writing and refinement stages

| package-and-margin | Coverage and deliverables | Price charged | Planning + labor cost stack | Estimated remaining amount |
|---|---|---|---|---|
| Hypothetical community event | 2 hours coverage, 1 planning call, edited gallery, 5-day turnaround | $500 | Shooting time $150, planning/admin $50, editing/delivery $100, travel $50, taxes reserve $50, gear recovery $50, writing and refinement stages $2.50 | $47.50 |
| Hypothetical reunion | 4 hours coverage, 1 planning call, edited gallery, 7-day turnaround | $1,500 | Shooting time $500, planning/admin $100, editing/delivery $250, travel $100, taxes reserve $150, gear recovery $150, assistant or support buffer $100, writing and refinement stages $2.50 | $147.50 |

One research source notes that some beginners start with one body until they can afford a second.

Research in the assigned material suggests that buying used gear or renting can reduce startup costs.

|    |
| :- |
"""


def _paid_patches():
    return (
        patch("ai_client.get_client", side_effect=AssertionError("paid client")),
        patch("ai_client.chat", side_effect=AssertionError("paid chat")),
        patch("ai_client.chat_json", side_effect=AssertionError("paid chat_json")),
    )


def _pdf_from_html(html: str) -> tuple[bytes, str]:
    from pypdf import PdfReader
    from services.pdf_export import _html_to_pdf_xhtml2pdf, _sanitize_pdf_local_link_uris

    try:
        pdf = _html_to_pdf_xhtml2pdf(html)
    except ValueError:
        patched = re.sub(r'\s*href="#chapter-\d+"', "", html)
        pdf = _html_to_pdf_xhtml2pdf(patched)
    pdf = _sanitize_pdf_local_link_uris(pdf)
    text = "\n".join((page.extract_text() or "") for page in PdfReader(BytesIO(pdf)).pages)
    return pdf, text


def _render(md: str, *, audience: str = "Beginner and intermediate photographers") -> str:
    design = build_ebook_design(theme_id="modern_practical", manuscript_digest="x")
    return render_designed_ebook_html(
        title="From First Booking to On-Site Prints",
        subtitle="A Practical Guide",
        author="Lonnie Brown",
        manuscript_md=md,
        design=design,
        audience=audience,
    )


class CustomerFacingSanitizerTests(unittest.TestCase):
    def test_defect1_concatenated_header_is_split_into_distinct_cells(self):
        html = (
            "<table><tr><td>Event niche / Typical client need / Guest interaction "
            "level / Planning complexity / Sales opportunity / Main beginner caution</td></tr>"
            "<tr><td>Weddings</td><td>Need</td><td>Med</td><td>High</td><td>Mod</td><td>Backup</td></tr></table>"
        )
        from services.ebook_book_layout import _decorate_structured_html

        out = _decorate_structured_html(html)
        soup = BeautifulSoup(out, "html.parser")
        cards = soup.select(".ebook-card")
        self.assertEqual(len(cards), 1)
        labels = [s.get_text(" ", strip=True) for s in cards[0].select(".ebook-card-label")]
        self.assertEqual(
            labels,
            [
                "Event niche:",
                "Typical client need:",
                "Guest interaction level:",
                "Planning complexity:",
                "Sales opportunity:",
                "Main beginner caution:",
            ],
        )
        self.assertIn("Weddings", cards[0].get_text(" ", strip=True))
        self.assertTrue(all("ebook-card" in (t.get("class") or []) for t in soup.find_all("table")))
        self.assertNotIn("<br", out.lower())
        self.assertNotIn("Event niche / Typical client need / Guest interaction", out)
        findings = inspect_html_tables(out)
        self.assertFalse(any(f["code"] == "concatenated_table_header" for f in findings))

    def test_defect1_wide_table_becomes_labeled_comparison_cards(self):
        html = _render(WIDE_TABLE_MD)
        soup = BeautifulSoup(html, "html.parser")
        self.assertIsNone(soup.find(class_="ebook-table-wide"))
        self.assertEqual(len(soup.select(".ebook-comparison")), 1)
        cards = soup.select(".ebook-card")
        self.assertEqual(len(cards), 2)
        self.assertEqual(soup.select_one(".ebook-comparison")["data-fields"], "6")
        labels = [s.get_text(" ", strip=True) for s in cards[0].select(".ebook-card-label")]
        self.assertEqual(labels[0], "Event niche:")
        self.assertEqual(labels[1], "Typical client need:")
        self.assertIn("Weddings", cards[0].get_text(" ", strip=True))
        self.assertNotIn("<br", html.lower())
        self.assertTrue(all("ebook-card" in (t.get("class") or []) for t in soup.find_all("table")))
        findings = inspect_html_tables(html)
        self.assertFalse(any(f["code"] in {"concatenated_table_header", "malformed_table_header"} for f in findings))

    def test_defect1_preflight_fails_header_body_mismatch(self):
        html = (
            '<table class="ebook-table"><thead><tr><th>A</th><th>B</th></tr></thead>'
            "<tbody><tr><td>1</td><td>2</td><td>3</td></tr></tbody></table>"
        )
        findings = inspect_html_tables(html)
        self.assertTrue(any(f["code"] == "malformed_table_header" for f in findings))

    def test_defect2_empty_markdown_tables_removed_and_never_rendered(self):
        md = "## Chapter 1\n\nKeep this paragraph.\n\n|    |\n| :- |\n\nStill here.\n"
        cleaned, report = sanitize_customer_manuscript(md)
        self.assertGreaterEqual(report["empty_tables_removed"], 1)
        self.assertNotRegex(cleaned, r"^\|\s*\|?\s*$", re.M)
        html = _render(cleaned)
        self.assertNotIn("chapter-last-keep", html)
        self.assertFalse(any(f["code"] == "empty_table" for f in inspect_html_tables(html)))
        self.assertNotIn("|    |", html)
        self.assertNotIn("| :- |", html)

    def test_defect2_keep_together_uses_div_not_empty_table(self):
        html = _render("## Chapter 1\n\nBody one.\n\nLast paragraph stays together.\n")
        self.assertIn("chapter-last-block", html)
        self.assertNotIn("chapter-last-keep", html)
        self.assertNotRegex(html, r"<table[^>]*chapter-last-block")
        self.assertRegex(html, r"<div[^>]*chapter-last-block")
        self.assertNotIn("|    |", html)
        self.assertEqual(len(BeautifulSoup(html, "html.parser").find_all("table")), 0)

    def test_defect3_factory_leakage_rewritten_and_margins_recalculated(self):
        cleaned, report = sanitize_customer_manuscript(LEAKY_MD)
        self.assertNotIn("MANDATORY DELIVERABLE", cleaned)
        self.assertNotIn("[inquiry-to-booking scenario]", cleaned)
        self.assertNotIn("$2.50 for writing and refinement stages", cleaned)
        self.assertNotIn("One research source notes", cleaned)
        self.assertNotIn("Research in the assigned material", cleaned)
        self.assertIn("From inquiry to a signed booking", cleaned)
        self.assertIn("Hypothetical package and margin scenario", cleaned)
        self.assertIn("| $50 |", cleaned)
        self.assertIn("| $150 |", cleaned)
        self.assertNotIn("$47.50", cleaned)
        self.assertNotIn("$147.50", cleaned)
        self.assertEqual(report["margin_recalculations"], list(MARGIN_RECALCULATIONS))
        leftover = detect_customer_facing_defects(cleaned)
        self.assertFalse(leftover, leftover)

    def test_defect3_preflight_fails_leaked_prompt_language(self):
        data = build_acceptance_project_data()
        data["content"] = "MANDATORY DELIVERABLE [inquiry-to-booking scenario]"
        data["ebook"] = data["content"]
        report = run_design_preflight(data, html="<p>MANDATORY DELIVERABLE</p>", pdf_bytes=b"")
        self.assertTrue(any(f.code == "customer_facing_leakage" for f in report.findings))

    def test_defect4_one_copyright_heading_and_sentence_case_audience(self):
        html = _render("## Chapter 1\n\nHello.\n")
        self.assertEqual(len(re.findall(r">Copyright<", html)), 1)
        self.assertNotIn("This interior is typeset from the approved manuscript", html)
        self.assertNotIn("Design does not rewrite manuscript content", html)
        self.assertIn("For beginner and intermediate photographers", html)
        self.assertEqual(len(re.findall(r"For beginner and intermediate photographers", html)), 1)
        self.assertNotIn("For Beginner and intermediate photographers", html)
        self.assertNotIn("Unnumbered", html)
        self.assertIn("All rights reserved", html)

    def test_defect5_contents_uses_internal_chapter_anchors(self):
        html = _render("## Chapter 1\n\nHello.\n\n## Chapter 2\n\nMore.\n")
        self.assertIn('href="#chapter-1"', html)
        self.assertIn('href="#chapter-2"', html)
        self.assertNotIn("127.0.0.1", html)
        self.assertNotIn("localhost", html)
        self.assertNotIn("ebook-workspace/", html)

    def test_defect6_sources_unescape_and_do_not_invent(self):
        md = (
            "## Chapter 1\n\nBody.\n\n**Sources**\n"
            "- https\\://startcosts.com/photography\n"
            "- https://www.mitsubishielectric.com/printer/dowmload-01\n"
        )
        html = _render(md)
        self.assertNotIn(r"https\://", html)
        self.assertNotIn(r"www\.", html)
        self.assertIn('href="https://startcosts.com/photography"', html)
        self.assertIn("https://www.mitsubishielectric.com/printer/dowmload-01", html)
        self.assertNotIn("https://example.com", html)
        self.assertEqual(
            unescape_source_url(r"https\://startcosts.com/photography"),
            "https://startcosts.com/photography",
        )

    def test_defect7_slug_headings_become_reader_facing_titles(self):
        self.assertEqual(
            polish_heading("Checklist: insurance-and-coi"),
            "Checklist: Insurance and certificate of insurance",
        )
        self.assertEqual(polish_heading("inquiry-to-signed-booking"), "From inquiry to a signed booking")
        self.assertEqual(polish_heading("dye-sub-printer-comparison"), "Dye-sub printer comparison")
        self.assertEqual(polish_heading("event-day-run-of-show"), "Event-day run of show")
        cleaned, _report = sanitize_customer_manuscript(
            "## Planning\n\n### Table: event-planning-timeline\n\n### file-backup-procedure\n"
        )
        self.assertIn("### Event-planning timeline", cleaned)
        self.assertIn("### File backup procedure", cleaned)
        self.assertNotIn("Table: event-planning-timeline", cleaned)

    def test_assigned_source_rewritten_and_duplicate_heading_dropped(self):
        md = (
            "## Finding Clients\n\n"
            "### From inquiry to a signed booking\n\n"
            "1. Receive the inquiry.\n\n"
            "### From inquiry to a signed booking\n\n"
            "**Example: turning an inquiry into a signed booking**\n\n"
            "A church event coordinator sends an inquiry.\n\n"
            "For compact on-site dye-sub printing, the assigned source supports that "
            "the **DNP QW410** is a dye-sublimation printer.\n"
        )
        cleaned, _report = sanitize_customer_manuscript(md)
        self.assertEqual(len(re.findall(r"From inquiry to a signed booking", cleaned)), 1)
        self.assertIn("A church event coordinator sends an inquiry", cleaned)
        self.assertNotIn("assigned source", cleaned.lower())
        self.assertIn("manufacturer documentation states that the **DNP QW410** is a dye-sublimation printer", cleaned)

    def test_four_column_timeline_stays_a_real_table(self):
        html = _render(FOUR_COL_MD)
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table", class_="ebook-table")
        self.assertIsNotNone(table)
        heads = [c.get_text(" ", strip=True) for c in table.find("tr").find_all("th")]
        self.assertEqual(heads, ["Stage", "When", "What to confirm", "Why it matters"])
        self.assertFalse(table.find("br"))
        body = table.find("tbody").find("tr") if table.find("tbody") else table.find_all("tr")[1]
        self.assertEqual(len(body.find_all(["td", "th"])), 4)
        self.assertFalse(soup.select(".ebook-comparison"))
        pdf, pdf_text = _pdf_from_html(html)
        self.assertIn("Stage", pdf_text)
        self.assertIn("What to confirm", pdf_text)
        self.assertIn("Inquiry", pdf_text)
        for sample in CONCATENATED_HEADER_SAMPLES:
            for line in pdf_text.splitlines():
                self.assertNotIn(sample, line)
        findings = inspect_rendered_ebook(html=html, pdf_text=pdf_text, pdf_bytes=pdf)
        self.assertFalse(findings, findings)

    def test_long_four_column_timeline_becomes_labeled_cards(self):
        html = _render(LONG_TIMELINE_MD)
        soup = BeautifulSoup(html, "html.parser")
        timeline = soup.select_one(".ebook-timeline")
        self.assertIsNotNone(timeline)
        self.assertEqual(timeline["data-fields"], "4")
        cards = timeline.select(".ebook-card")
        self.assertEqual(len(cards), 8)
        labels = [s.get_text(" ", strip=True) for s in cards[0].select(".ebook-card-label")]
        self.assertEqual(labels, ["Stage:", "When:", "What to confirm:", "Why it matters:"])
        stages = [c.select_one(".ebook-card-value").get_text(" ", strip=True) for c in cards]
        self.assertEqual(stages, list(TIMELINE_STAGES))
        self.assertFalse(any(th.find("br") for th in soup.find_all("th")))
        grid = [
            t
            for t in soup.find_all("table")
            if "ebook-table" in (t.get("class") or []) and "ebook-card" not in (t.get("class") or [])
        ]
        self.assertFalse(grid)
        pdf, pdf_text = _pdf_from_html(html)
        compact = re.sub(r"\s+", "", html + pdf_text)
        self.assertNotIn("StageWhenWhat to confirmWhy it matters", compact)
        self.assertIn("Stage:", pdf_text)
        self.assertIn("Initial inquiry", pdf_text)
        self.assertIn("Breakdown", pdf_text)
        findings = inspect_rendered_ebook(html=html, pdf_text=pdf_text, pdf_bytes=pdf)
        self.assertFalse(findings, findings)

    def test_five_six_seven_column_tables_render_as_cards(self):
        cases = (
            (FIVE_COL_MD, 5, "Startup lane:", "Lean start"),
            (WIDE_TABLE_MD, 6, "Event niche:", "Weddings"),
            (SEVEN_COL_MD, 7, "Kit level:", "Starter"),
            (LONG_HEADER_SIX_MD, 6, "Sales opportunity for on-site prints:", "Moderate"),
        )
        for md, fields, first_label, first_value in cases:
            html = _render(md)
            soup = BeautifulSoup(html, "html.parser")
            with self.subTest(fields=fields):
                self.assertEqual(len(soup.select(".ebook-comparison")), 1)
                self.assertEqual(soup.select_one(".ebook-comparison")["data-fields"], str(fields))
                card = soup.select_one(".ebook-card")
                labels = [s.get_text(" ", strip=True) for s in card.select(".ebook-card-label")]
                self.assertEqual(len(labels), fields)
                self.assertIn(first_label, labels)
                self.assertEqual(labels[0].endswith(":"), True)
                self.assertIn(first_value, card.get_text(" ", strip=True))
                self.assertNotIn("<br", html.lower())
                self.assertFalse(any(th.find("br") for th in soup.find_all("th")))
                pdf, pdf_text = _pdf_from_html(html)
                self.assertIn(first_label.rstrip(":"), pdf_text)
                self.assertIn(first_value, pdf_text)
                for sample in CONCATENATED_HEADER_SAMPLES:
                    for line in pdf_text.splitlines():
                        self.assertNotIn(sample, line)
                findings = inspect_rendered_ebook(html=html, pdf_text=pdf_text, pdf_bytes=pdf)
                self.assertFalse(findings, findings)

    def test_rendered_html_and_pdf_use_cards_not_concatenated_headers(self):
        html = _render(WIDE_TABLE_MD)
        soup = BeautifulSoup(html, "html.parser")
        self.assertEqual(len(soup.select(".ebook-card")), 2)
        self.assertTrue(all("ebook-card" in (t.get("class") or []) for t in soup.find_all("table")))
        self.assertNotIn("about:srcdoc", html)
        self.assertIn("#chapter-1", html)
        self.assertNotIn("127.0.0.1", html)
        self.assertNotIn("ebook-workspace/", html)
        pdf, pdf_text = _pdf_from_html(html)
        findings = inspect_rendered_ebook(html=html, pdf_text=pdf_text, pdf_bytes=pdf)
        self.assertFalse(findings, findings)
        self.assertIn("Event niche:", pdf_text)
        self.assertIn("Weddings", pdf_text)


class CustomerFacingPreflightAndLiveTests(unittest.TestCase):
    def test_preflight_fails_empty_table_and_localhost_html(self):
        data = build_acceptance_project_data()
        data["content"] = "## Chapter 1\n\nHello."
        data["ebook"] = data["content"]
        html = (
            '<table class="ebook-table"><tr><th></th></tr><tr><td></td></tr></table>'
            '<a href="http://127.0.0.1:5055/ebook-workspace/4249/full-preview#chapter-1">Ch 1</a>'
        )
        report = run_design_preflight(data, html=html, pdf_bytes=b"")
        codes = {f.code for f in report.findings}
        self.assertIn("empty_table", codes)
        self.assertIn("local_preview_url", codes)

    def test_inspect_output_requires_zero_defects_on_clean_book(self):
        html = _render(WIDE_TABLE_MD + "\n\n**Sources**\n- https://startcosts.com/photography\n")
        findings = inspect_customer_facing_output(
            manuscript_md=WIDE_TABLE_MD,
            html=html,
            pdf_text="Chapter 1 Event niche Typical client need",
        )
        self.assertFalse(findings, findings)

    def test_live_4249_cover_and_theme_preserved(self):
        row = database.get_project(LIVE_4249)
        self.assertIsNotNone(row, "project #4249 must exist")
        data = row["data"]
        cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
        src = cover.get("source") if isinstance(cover.get("source"), dict) else {}
        design = data.get("ebook_design") if isinstance(data.get("ebook_design"), dict) else {}
        self.assertEqual(str(src.get("sha256") or ""), EXPECTED_COVER_SHA)
        self.assertEqual(str(cover.get("cover_digest") or ""), EXPECTED_COVER_DIGEST)
        self.assertEqual(str(design.get("theme_id") or data.get("design_theme") or ""), "modern_practical")
        self.assertEqual(str(data.get("title") or ""), "From First Booking to On-Site Prints")
        self.assertFalse(data.get("export_ready"))

    def test_live_4249_rendered_html_meets_output_gate(self):
        row = database.get_project(LIVE_4249)
        self.assertIsNotNone(row, "project #4249 must exist")
        data = row["data"]
        html = str(data.get("ebook_preview_html") or data.get("preview_html") or "")
        md = str(data.get("content") or data.get("ebook") or "")
        soup = BeautifulSoup(html, "html.parser")
        self.assertIn("From First Booking to On-Site Prints", html)
        comparisons = [
            n for n in soup.select(".ebook-comparison") if "ebook-timeline" not in (n.get("class") or [])
        ]
        self.assertEqual(len(comparisons), 5)
        field_counts = sorted(int(n["data-fields"]) for n in comparisons)
        self.assertEqual(field_counts, [5, 5, 6, 6, 7])
        timeline = soup.select_one(".ebook-timeline")
        self.assertIsNotNone(timeline)
        self.assertEqual(timeline["data-fields"], "4")
        cards = timeline.select(".ebook-card")
        self.assertEqual(len(cards), 8)
        labels = [s.get_text(" ", strip=True) for s in cards[0].select(".ebook-card-label")]
        self.assertEqual(labels, ["Stage:", "When:", "What to confirm:", "Why it matters:"])
        stages = [c.select_one(".ebook-card-value").get_text(" ", strip=True) for c in cards]
        self.assertEqual(stages[0], "Initial inquiry")
        self.assertEqual(stages[-1], "Breakdown")
        self.assertEqual(len(stages), 8)
        grid = [
            t
            for t in soup.find_all("table")
            if "ebook-table" in (t.get("class") or []) and "ebook-card" not in (t.get("class") or [])
        ]
        self.assertFalse(grid)
        first_labels = [
            sec.select_one(".ebook-card-label").get_text(" ", strip=True) for sec in comparisons
        ]
        self.assertEqual(
            first_labels,
            [
                "Event niche:",
                "Startup lane:",
                "Kit level:",
                "Package:",
                "Printer:",
            ],
        )
        self.assertFalse(any(th.find("br") for th in soup.find_all("th")))
        self.assertNotIn("about:srcdoc", html)
        self.assertNotIn("Unnumbered", html)
        self.assertEqual(len(re.findall(r"For beginner and intermediate photographers", html, re.I)), 1)
        inquiry = [
            h.get_text(" ", strip=True)
            for h in soup.select(".chapter-page h3, .chapter-page h4")
            if h.get_text(" ", strip=True).lower() == "from inquiry to a signed booking"
        ]
        self.assertEqual(len(inquiry), 1)
        self.assertNotIn("assigned source", md.lower())
        self.assertNotIn("assigned source", html.lower())
        self.assertIn("DNP QW410", md)
        self.assertNotIn("127.0.0.1", html)
        self.assertNotIn("ebook-workspace/", html)
        for a in soup.select(".toc-list a"):
            href = str(a.get("href") or "")
            self.assertTrue(href.startswith("#chapter-"), href)
        pdf, pdf_text = _pdf_from_html(html)
        self.assertIn("From First Booking to On-Site Prints", html)
        self.assertIn("From First Booking to On-Site Prints", pdf_text)
        compact = re.sub(r"\s+", "", html + "\n" + pdf_text)
        self.assertNotIn("StageWhenWhat to confirmWhy it matters", compact)
        self.assertIn("Stage:", pdf_text)
        self.assertIn("Initial inquiry", pdf_text)
        self.assertIn("Breakdown", pdf_text)
        self.assertNotIn("assigned source", pdf_text.lower())
        self.assertNotIn("Unnumbered", pdf_text)
        self.assertNotIn("127.0.0.1", pdf_text)
        self.assertNotIn("ebook-workspace", pdf_text)
        for sample in CONCATENATED_HEADER_SAMPLES:
            for line in pdf_text.splitlines():
                self.assertNotIn(sample, line)
        findings = inspect_customer_facing_output(
            manuscript_md=md, html=html, pdf_text=pdf_text, pdf_bytes=pdf
        )
        self.assertFalse(findings, findings)


if __name__ == "__main__":
    for p in _paid_patches():
        p.start()
    try:
        unittest.main()
    finally:
        pass
