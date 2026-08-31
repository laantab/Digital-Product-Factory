"""Convert saved product / publishing preview HTML into a polished PDF."""
from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import logging
import os
import re
from typing import Any

from bs4 import BeautifulSoup, NavigableString, Tag

from services.ebook_package import (
    EXPORTS_DIR,
    _split_chapters,
    clean_product_summary,
    fix_inline_hyphen_lists_html,
)
from services.publishing import build_publishing_pdf_css, detect_template_key
from services.visual_fallback import (
    looks_like_prompt,
    package_id_from_url,
    pdf_image_data_uri,
    pdf_image_fallback_html,
    safe_caption,
    image_asset_path,
)

PDF_EXPORT_VERSION = "visual-v6"  # embedded TTF, full-bleed cover, 12pt body, compressed images


# ---------------------------------------------------------------------------
# Professional AI Cover Generator (ReportLab Canvas — no API calls)
# ---------------------------------------------------------------------------

def _generate_ai_cover_pdf_bytes(title: str, subtitle: str) -> bytes:
    """Generate a professional AI/technology cover using ReportLab Canvas.

    Draws a dark navy-to-indigo gradient background with circuit-board
    network lines, glowing nodes, and translucent arc overlays.
    Title and subtitle are centered in white.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas as rl_canvas

    buf = io.BytesIO()
    W, H = letter  # 612 x 792

    c = rl_canvas.Canvas(buf, pagesize=letter)
    c.setTitle(title or "Ebook")

    # ── Dark gradient background (solid dark base) ──────────────────────────
    c.setFillColorRGB(0.08, 0.05, 0.18)  # deep navy
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # ── Gradient overlay (indigo band at bottom) ─────────────────────────────
    c.setFillColorRGB(0.18, 0.12, 0.42)
    c.rect(0, 0, W, H * 0.35, fill=1, stroke=0)

    # ── Subtle grid overlay ─────────────────────────────────────────────────
    c.setStrokeColorRGB(0.3, 0.22, 0.6)
    c.setLineWidth(0.3)
    for x in range(0, int(W) + 1, 40):
        c.line(x, 0, x, H)
    for y in range(0, int(H) + 1, 40):
        c.line(0, y, W, y)

    # ── Circuit network lines ───────────────────────────────────────────────
    # Horizontal tracks
    c.setStrokeColorRGB(0.45, 0.35, 0.85)
    c.setLineWidth(1.5)
    h_tracks = [120, 200, 300, 420, 540, 640, 720]
    for y in h_tracks:
        c.line(0, y, W, y)

    # Vertical tracks
    v_tracks = [60, 140, 240, 360, 460, 560, W]
    for x in v_tracks:
        c.line(x, 0, x, H)

    # ── Glowing connection nodes ────────────────────────────────────────────
    node_positions = [
        (140, 200), (240, 120), (360, 300), (460, 200), (560, 420),
        (60, 300), (140, 420), (240, 540), (360, 640), (460, 540),
        (60, 640), (560, 120), (360, 200), (460, 720),
    ]
    for nx, ny in node_positions:
        # Outer glow
        c.setFillColorRGB(0.55, 0.42, 0.95)
        c.circle(nx, ny, 7, fill=1, stroke=0)
        # Inner bright dot
        c.setFillColorRGB(0.85, 0.72, 1.0)
        c.circle(nx, ny, 3.5, fill=1, stroke=0)
        # Highlight
        c.setFillColorRGB(1.0, 1.0, 1.0)
        c.circle(nx, ny, 1.5, fill=1, stroke=0)

    # ── Arc overlays (translucent arcs for depth) ───────────────────────────
    c.setStrokeColorRGB(0.5, 0.38, 0.9)
    c.setLineWidth(0.8)
    c.setFillColorRGB(0.08, 0.05, 0.18)
    # Large arc top-right
    c.arc(W * 0.62, H * 0.55, W - 10, H - 20, 0, 180)
    # Small arc bottom-left
    c.arc(20, 10, W * 0.32, H * 0.38, 180, 360)
    # Mid arc
    c.arc(W * 0.5, H * 0.15, W - 40, H * 0.72, 0, 180)

    # ── Translucent panels ───────────────────────────────────────────────────
    c.setFillColorRGB(0.18, 0.12, 0.38)
    c.setStrokeColorRGB(0.5, 0.4, 0.9)
    c.setLineWidth(1)
    # Right panel
    c.roundRect(W * 0.72, H * 0.08, W * 0.22, H * 0.84, 12, fill=1, stroke=1)
    # Left accent bar
    c.setFillColorRGB(0.38, 0.25, 0.72)
    c.roundRect(18, H * 0.12, 10, H * 0.76, 5, fill=1, stroke=0)

    # ── Content panel (centered) ─────────────────────────────────────────────
    panel_x = W * 0.08
    panel_y = H * 0.18
    panel_w = W * 0.6
    panel_h = H * 0.64
    c.setFillColorRGB(0.12, 0.08, 0.26)
    c.setStrokeColorRGB(0.5, 0.38, 0.88)
    c.setLineWidth(1.5)
    c.roundRect(panel_x, panel_y, panel_w, panel_h, 16, fill=1, stroke=1)

    # Inner border glow
    c.setStrokeColorRGB(0.6, 0.48, 1.0)
    c.setLineWidth(0.5)
    c.roundRect(panel_x + 4, panel_y + 4, panel_w - 8, panel_h - 8, 14, fill=0, stroke=1)

    # ── "EBOOK" badge ───────────────────────────────────────────────────────
    c.setFillColorRGB(0.55, 0.42, 0.95)
    c.setStrokeColorRGB(0.75, 0.65, 1.0)
    c.setLineWidth(1)
    badge_w, badge_h = 80, 22
    badge_x = (W - badge_w) / 2
    badge_y = H * 0.72
    c.roundRect(badge_x, badge_y, badge_w, badge_h, 11, fill=1, stroke=1)
    c.setFillColorRGB(0.95, 0.92, 1.0)
    from reportlab.lib.utils import simpleSplit
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(W / 2, badge_y + 7, "EBOOK")

    # ── Title ───────────────────────────────────────────────────────────────
    from reportlab.lib.utils import simpleSplit
    c.setFillColorRGB(1.0, 1.0, 1.0)
    c.setFont("Helvetica-Bold", 26)
    # Split title into lines to handle long titles
    max_title_w = panel_w - 48
    title_lines = simpleSplit(title or "Untitled", "Helvetica-Bold", 26, max_title_w)
    line_h = 34
    title_start_y = H * 0.62
    for i, line in enumerate(title_lines):
        ty = title_start_y - i * line_h
        c.drawCentredString(W / 2, ty, line)

    # ── Horizontal rule ─────────────────────────────────────────────────────
    rule_y = title_start_y - len(title_lines) * line_h - 10
    c.setStrokeColorRGB(0.6, 0.48, 1.0)
    c.setLineWidth(1.5)
    rule_start_x = panel_x + 30
    rule_end_x = panel_x + panel_w - 30
    c.line(rule_start_x, rule_y, rule_end_x, rule_y)

    # ── Subtitle ─────────────────────────────────────────────────────────────
    c.setFillColorRGB(0.78, 0.72, 0.95)
    c.setFont("Helvetica", 12)
    sub_lines = simpleSplit(subtitle or "", "Helvetica", 12, max_title_w)
    sub_start_y = rule_y - 18
    for i, line in enumerate(sub_lines):
        sy = sub_start_y - i * 18
        c.drawCentredString(W / 2, sy, line)

    # ── Decorative corner accents ───────────────────────────────────────────
    c.setFillColorRGB(0.6, 0.48, 1.0)
    c.setStrokeColorRGB(0.7, 0.58, 1.0)
    c.setLineWidth(1.5)
    # Top-left corner
    c.line(panel_x + 12, panel_y + panel_h - 8, panel_x + 12, panel_y + panel_h - 28)
    c.line(panel_x + 12, panel_y + panel_h - 8, panel_x + 32, panel_y + panel_h - 8)
    # Bottom-right corner
    c.line(panel_x + panel_w - 12, panel_y + 8, panel_x + panel_w - 12, panel_y + 28)
    c.line(panel_x + panel_w - 12, panel_y + 8, panel_x + panel_w - 32, panel_y + 8)

    # ── Footer line ─────────────────────────────────────────────────────────
    c.setStrokeColorRGB(0.4, 0.3, 0.75)
    c.setLineWidth(0.5)
    c.line(panel_x + 30, panel_y + 30, panel_x + panel_w - 30, panel_y + 30)
    c.setFillColorRGB(0.6, 0.5, 0.85)
    c.setFont("Helvetica", 8)
    c.drawCentredString(W / 2, panel_y + 16, "AI Model Selection Guide")

    c.save()
    return buf.getvalue()


def _strip_cover_section_from_pdf(pdf_bytes: bytes) -> bytes:
    """Remove page 1 from a PDF bytes stream (used when replacing the HTML cover)."""
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    # Skip page 0 (the HTML cover), keep the rest
    for page in reader.pages[1:]:
        writer.add_page(page)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _prepend_pdf_bytes(cover_bytes: bytes, body_bytes: bytes) -> bytes:
    """Prepend a cover PDF before body PDF and return merged result."""
    from pypdf import PdfReader, PdfWriter

    cover_reader = PdfReader(io.BytesIO(cover_bytes))
    body_reader = PdfReader(io.BytesIO(body_bytes))
    writer = PdfWriter()
    for page in cover_reader.pages:
        writer.add_page(page)
    for page in body_reader.pages:
        writer.add_page(page)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()

_logger = logging.getLogger(__name__)


def _log_validation(pdf_bytes: bytes) -> None:
    """Run ebook QA validator on the generated PDF (non-blocking, always logs)."""
    try:
        from services.ebook_qa_validator import validate_ebook_pdf  # lazy to avoid circular imports

        md5 = hashlib.md5(pdf_bytes).hexdigest()
        result = validate_ebook_pdf(pdf_bytes, pdf_md5=md5)
        if not result.passed:
            _logger.error("[EBOOK-QA] PDF %s FAILED:\n%s", md5, result.summary())
            print(f"\n[EBOOK-QA ERROR] MD5={md5} Pages={result.page_count}")
            for c in result.checks:
                if not c.passed:
                    print(f"  [FAIL] {c.name}: {c.message}")
        else:
            _logger.info("[EBOOK-QA] PDF %s passed all checks", md5)
    except Exception:
        _logger.exception("[EBOOK-QA] Validator crashed -- non-blocking, continuing")

_PDF_IMAGE_HASHES: list[int] = []


def _reset_pdf_image_dedupe() -> None:
    _PDF_IMAGE_HASHES.clear()


_PDF_CSS = """
@page { size: letter; margin: 1.05in 0.75in 1.05in 0.75in; }
/* EbookSans is registered via @font-face + reportlab TTFont. Do not set glyph tracking. */
body { margin: 0; padding: 0; font-family: EbookSans, Helvetica, Arial, sans-serif; color: #111827;
  font-size: 12pt; line-height: 1.55; }
.pdf-page { display: block; }

/* Cover */
.cover-page { page-break-after: always; padding: 0; margin: 0; }
.cover-shell { width: 100%; border-collapse: collapse; }
.cover-shell td { background-color: #0f766e; color: #ffffff; padding: 48pt 40pt 40pt; vertical-align: top; }
.cover-top { text-align: left; padding-bottom: 20pt; }
.cover-type { display: inline-block; font-size: 9pt; text-transform: uppercase; font-weight: bold;
  border: 1pt solid #99f6e4; padding: 5pt 12pt; margin-bottom: 16pt; color: #ecfdf5; }
.cover-rule { width: 48pt; height: 3pt; background-color: #fbbf24; margin: 0 0 16pt; }
.cover-title { font-size: 26pt; font-weight: bold; line-height: 1.15; margin: 0 0 12pt; color: #ffffff; }
.cover-subtitle { font-size: 12pt; line-height: 1.45; margin: 0 0 10pt; max-width: 92%; color: #ccfbf1; }
.cover-author { font-size: 10pt; color: #a5f3fc; margin-top: 8pt; }
.cover-mockup { margin-top: 18pt; }
.cover-browser { border-collapse: collapse; width: 100%; border: 1pt solid #99f6e4; overflow: hidden; }
.cover-browser-bar { background-color: #e2e8f0; padding: 7pt 12pt; font-size: 8pt; color: #475569; font-weight: bold; }
.cover-browser-dots { color: #94a3b8; margin-right: 8pt; }
.cover-browser-body { background-color: #ffffff; padding: 14pt; color: #1e293b; }
.cover-search { background-color: #f8fafc; border: 1pt solid #cbd5e1; padding: 9pt 16pt;
  font-size: 9pt; color: #64748b; text-align: left; margin-bottom: 12pt; }
.cover-cards-row { width: 100%; border-collapse: separate; border-spacing: 8pt 0; }
.cover-mini-card { background-color: #fafafa; border: 1pt solid #e2e8f0; padding: 10pt 8pt; vertical-align: top; }
.cover-mini-img { background-color: #99f6e4; height: 36pt; margin-bottom: 6pt; }
.cover-mini-title { font-size: 8pt; font-weight: bold; color: #115e59; }
.cover-mini-tag { font-size: 7pt; color: #0f766e; margin-top: 3pt; }
.cover-checklist { font-size: 8pt; color: #059669; text-align: center; padding-top: 12pt; font-weight: bold; }
.cover-analytics { font-size: 8pt; color: #64748b; text-align: center; padding-top: 6pt; }

/* Inside title */
.title-page { page-break-after: always; text-align: center; padding-top: 0.55in; }
.title-page .title-main { font-size: 26pt; color: #134e4a; margin: 0 0 10pt; }
.title-page .title-sub { font-size: 13pt; color: #334155; margin: 0 auto 16pt; max-width: 85%; }
.title-page .summary-lead { font-size: 12pt; color: #111827; text-align: left; margin: 18pt auto 0; max-width: 92%; line-height: 1.55; }
.title-disclaimer { font-size: 10pt; color: #334155; margin-top: 22pt; font-style: italic; }
.legal-page { page-break-after: always; padding-top: 0.1in; }
.legal-page h2 { font-size: 20pt; color: #134e4a; margin: 0 0 14pt; }
.legal-page p { font-size: 12pt; color: #111827; line-height: 1.55; margin: 0 0 10pt; }

/* TOC — own page; never share a sheet with copyright (rebuild replaces TOC page). */
.toc-page { page-break-after: always; padding-top: 0.15in; }
.toc-page h2 { font-size: 22pt; color: #134e4a; margin: 0 0 16pt; border: none; padding: 0; }
.toc-list { list-style: none; margin: 0; padding: 0; }
.toc-list li { padding: 7pt 0; border-bottom: 1pt solid #e2e8f0; font-size: 11pt; color: #334155; }
.toc-list a { color: #0f766e; text-decoration: none; font-weight: bold; }
.toc-page-num { float: right; color: #64748b; font-weight: normal; }

/* Chapters */
.chapter-page { page-break-before: always; padding-top: 0.12in; }
.chapter-num { display: block; font-size: 9pt; font-weight: bold; text-transform: uppercase; color: #0f766e; margin-bottom: 6pt; }
.chapter-title, .chapter-page > h2:first-of-type { font-size: 24pt; color: #134e4a; margin: 0 0 14pt;
  padding-bottom: 8pt; border-bottom: 2pt solid #99f6e4; }
h3 { font-size: 15pt; color: #115e59; margin: 16pt 0 8pt; }
p { margin: 0 0 10pt; display: block; font-size: 12pt; color: #111827; }
.pdf-callout { border-left: 3pt solid #0f766e; background: #f0fdfa; padding: 10pt 12pt; margin: 12pt 0; }
table.pdf-callout { width: 100%; border-collapse: collapse; padding: 0; }
td.pdf-callout-cell { border: none; background: #f0fdfa; padding: 10pt 12pt; }
table.pdf-h3-keep, table.pdf-p-keep, table.pdf-list-keep, table.pdf-li-keep {
  width: 100%; margin: 0 0 2pt 0; border: none; border-collapse: collapse;
}
td.pdf-h3-cell, td.pdf-p-cell, td.pdf-list-cell, td.pdf-li-cell { border: none; background: transparent; padding: 3pt 0; }
td.pdf-h3-cell { font-size: 15pt; color: #115e59; font-weight: bold; padding: 10pt 0 4pt; }
td.pdf-p-cell { font-size: 12pt; color: #111827; line-height: 1.55; padding: 4pt 0 8pt; }
td.pdf-li-cell { padding: 3pt 0 3pt 12pt; font-size: 12pt; color: #111827; line-height: 1.5; }
td.pdf-list-cell { font-size: 12pt; color: #111827; }
ul, ol { margin: 0 0 10pt 16pt; padding-left: 14pt; }
li { margin: 4pt 0; display: block; }
ul { list-style-type: disc; }
ol { list-style-type: decimal; }

/* Tables */
table, .va-table { border-collapse: collapse; width: 100%; margin: 10pt 0; page-break-inside: avoid; }
th, td { border: 1pt solid #cbd5e1; padding: 6pt 8pt; text-align: left; font-size: 9.5pt; vertical-align: top; }
th { background: #f5f3ff; color: #4c1d95; font-weight: bold; }
tbody tr:nth-child(even) td { background: #faf9ff; }

/* 4+ column card table: inner mini-table for label+value per cell (PDF-safe) */
td.tcard-cell { padding: 6pt 8pt; background: #f8fafc; vertical-align: top; border: 1pt solid #cbd5e1; }
.tcard-inner { width: 100%; border-collapse: collapse; }
.tcard-inner td { padding: 2pt 0; border: none; background: transparent; vertical-align: top; }
.tcard-inner td.tcard-hdr { font-size: 8pt; font-weight: bold; color: #6d28d9; text-transform: uppercase; }
.tcard-inner td.tcard-val { font-size: 9.5pt; color: #1e293b; line-height: 1.4; }

/* Visual aids -- keep title, content, and caption on one page */
.pdf-visual-keep { page-break-inside: avoid !important; break-inside: avoid !important;
  margin: 14pt 0; width: 100%; border-collapse: collapse; }
.pdf-visual-frame { page-break-inside: avoid !important; break-inside: avoid !important;
  border-collapse: collapse; width: 100%; border: 1pt solid #e2e8f0; border-left: 4pt solid #7c3aed;
  background-color: #fafafa; }
.pdf-visual-block { padding: 12pt 14pt; page-break-inside: avoid !important; break-inside: avoid !important;
  vertical-align: top; }
.visual-aid { border: 1pt solid #e2e8f0; border-left: 4pt solid #7c3aed; border-radius: 6pt;
  padding: 12pt 14pt; margin: 14pt 0; background-color: #fafafa;
  page-break-inside: avoid !important; break-inside: avoid !important; }
.pdf-visual-title { font-size: 12pt; font-weight: bold; color: #312e81; margin: 0 0 8pt;
  page-break-after: avoid !important; break-after: avoid !important; }
.pdf-visual-body { page-break-inside: avoid !important; break-inside: avoid !important;
  page-break-before: avoid !important; break-before: avoid !important; }
.pdf-visual-caption, .pdf-visual-block .va-caption { font-size: 9pt; color: #64748b; font-style: italic;
  margin: 8pt 0 0; page-break-before: avoid !important; break-before: avoid !important; }
.pdf-visual-img { max-width: 100%; max-height: 2.75in; height: auto; display: block;
  margin: 4pt auto 6pt; page-break-inside: avoid !important; page-break-before: avoid !important; }
.pdf-bar-chart, .pdf-pie-chart, .pdf-flow-diagram, .pdf-info-card, .pdf-listing-mock, .pdf-principles {
  page-break-inside: avoid !important; break-inside: avoid !important; }
.va-label { font-size: 8pt; font-weight: bold; text-transform: uppercase;
  color: #7c3aed; margin-bottom: 6pt; }
.va-title { font-size: 12pt; font-weight: bold; color: #312e81; margin-bottom: 8pt; }
.va-caption { font-size: 9pt; color: #64748b; font-style: italic; margin-top: 8pt; }
.va-tip-box { border-left-color: #0d9488; background: #f0fdfa; }
.va-action-step-box { border-left-color: #d97706; background: #fffbeb; }
.va-worksheet-box { border-left-color: #2563eb; background: #eff6ff; }
.va-steps { margin: 0; padding-left: 18pt; }
.va-checklist { list-style: none; margin: 0; padding: 0; }
.va-checklist li { margin: 6pt 0; padding-left: 16pt; position: relative; }
.va-checklist li:before { content: "\\2610"; position: absolute; left: 0; color: #7c3aed; }

.pdf-bar-chart { margin: 8pt 0; border: 1pt solid #cbd5e1; background-color: #ffffff; width: 100%; }
.pdf-bar-chart-wrap { border: 1pt solid #e2e8f0; background-color: #f8fafc; padding: 10pt 8pt 6pt; }
.pdf-bar-axis { font-size: 7pt; color: #94a3b8; text-align: right; padding-right: 6pt; vertical-align: bottom; width: 16pt; }
.pdf-bar-plot { vertical-align: bottom; }
.pdf-bar-cell { vertical-align: bottom; text-align: center; padding: 0 6pt; }
.pdf-bar-fill { width: 22pt; margin: 0 auto; }
.pdf-bar-num { font-size: 8pt; font-weight: bold; color: #312e81; margin-bottom: 4pt; }
.pdf-bar-lbl { font-size: 7.5pt; color: #475569; margin-top: 5pt; font-weight: bold; }
.pdf-bar-baseline { border-top: 1pt solid #cbd5e1; height: 1pt; font-size: 1pt; }
.pdf-pie-chart { margin: 8pt 0; border: 1pt solid #e2e8f0; width: 100%; }
.pdf-pie-seg { text-align: center; vertical-align: middle; color: #ffffff; padding: 10pt 4pt; }
.pdf-pie-lbl { font-size: 8pt; font-weight: bold; }
.pdf-pie-pct { font-size: 11pt; font-weight: bold; margin-top: 2pt; }
.pdf-flow-diagram { margin: 8pt auto; max-width: 85%; }
.pdf-flow-box-cell { text-align: center; padding: 3pt 0; }
.pdf-flow-box { background: #ede9fe; border: 1pt solid #c4b5fd; border-radius: 4pt; padding: 8pt 10pt;
  font-size: 9pt; color: #3730a3; font-weight: bold; }
.pdf-flow-arrow-cell { text-align: center; color: #7c3aed; font-size: 11pt; padding: 2pt 0; }
.pdf-info-card { border: 1pt solid #ddd6fe; background: #faf5ff; border-radius: 6pt; padding: 12pt; margin: 6pt 0; }
.pdf-formula-row { text-align: center; font-size: 9pt; font-weight: bold; color: #312e81; }
.pdf-formula-part { display: inline-block; background: #ede9fe; border: 1pt solid #c4b5fd; border-radius: 4pt;
  padding: 6pt 8pt; margin: 3pt; }
.pdf-formula-sep { color: #7c3aed; font-weight: bold; margin: 0 2pt; }
.pdf-formula-note { font-size: 8pt; color: #64748b; text-align: center; margin-top: 8pt; }
.pdf-principles td { background: #f5f3ff; border: 1pt solid #ddd6fe; padding: 10pt; text-align: center;
  font-size: 9pt; vertical-align: top; width: 33%; }
.pdf-listing-mock { border: 1pt solid #e2e8f0; border-radius: 8pt; padding: 12pt; background-color: #ffffff; }
.pdf-listing-img { background-color: #ddd6fe; height: 64pt; border-radius: 6pt; vertical-align: top; }
.pdf-listing-title { font-size: 11pt; font-weight: bold; color: #1e293b; line-height: 1.3; }
.pdf-listing-stars { font-size: 9pt; color: #d97706; margin-top: 4pt; }
.pdf-listing-meta { font-size: 8pt; color: #64748b; margin-top: 3pt; }
.pdf-listing-price { font-size: 12pt; font-weight: bold; color: #059669; margin-top: 6pt; }
.pdf-listing-ship { font-size: 8pt; color: #475569; margin-top: 8pt; padding-top: 8pt; border-top: 1pt solid #e2e8f0; }
.pdf-listing-trust { display: inline-block; font-size: 7.5pt; font-weight: bold; color: #4338ca; background-color: #ede9fe;
  border: 1pt solid #c4b5fd; border-radius: 10pt; padding: 4pt 10pt; margin-top: 8pt; }
.pdf-listing-cta { font-size: 8pt; font-weight: bold; color: #ffffff; background-color: #7c3aed; border-radius: 4pt;
  padding: 6pt 12pt; margin-top: 8pt; text-align: center; }
.pdf-table { border-collapse: collapse; border: 1pt solid #cbd5e1; margin: 8pt 0; }
.pdf-table td { border: 1pt solid #cbd5e1; padding: 6pt 8pt; font-size: 10pt; vertical-align: top; }
.pdf-table tr:nth-child(even) td { background: #faf9ff; }

.summary-page, .action-page, .resources-page { page-break-before: always; }
.summary-page h2, .action-page h2, .resources-page h2 { font-size: 20pt; color: #1e1b4b; margin: 0 0 14pt; }

img { max-width: 100%; height: auto; max-height: 4in; display: block; margin: 8pt auto; }
img.pdf-visual-img { max-height: 2.75in; margin: 4pt auto 6pt; }
.page-foot, .va-img-fallback, .va-img-spinner, .va-img-note { display: none !important; }

/* Back matter -- section separation and worksheet styling */
.bm-section { border-top: 3pt solid #ede9fe; margin-top: 20pt; padding-top: 14pt; page-break-before: always; }
.bm-label { display: inline-block; background: #ecfdf5; color: #0f766e; font-weight: bold;
  font-size: 9pt; text-transform: uppercase;
  padding: 4pt 10pt; border-radius: 999pt; margin-bottom: 10pt; }
.bm-title { font-size: 16pt; font-weight: bold; color: #1e1b4b; margin: 0 0 10pt; }
.bm-intro { font-size: 10pt; color: #475569; margin-bottom: 12pt; }
.bm-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8pt; }
.bm-point { background: #f8fafc; border: 1pt solid #e2e8f0; border-radius: 6pt; padding: 10pt 12pt; }
.bm-point-title { font-size: 9pt; font-weight: bold; color: #312e81; margin-bottom: 4pt; }
.bm-point-body { font-size: 9pt; color: #475569; }
.bm-section.worksheet-page .bm-title { font-size: 14pt; margin-bottom: 10pt; }
.faq-list { display: flex; flex-direction: column; gap: 10pt; }
.faq-item { border: 1pt solid #e2e8f0; border-radius: 6pt; padding: 10pt 12pt; background: #fff; }
.faq-q { font-size: 10pt; font-weight: bold; color: #1e1b4b; margin-bottom: 4pt; }
.faq-a { font-size: 10pt; color: #475569; line-height: 1.5; }
.ws-table-wrap { overflow-x: auto; margin-bottom: 8pt; }
.ws-table { border-collapse: collapse; width: 100%; font-size: 9pt; }
.ws-table-fixed { table-layout: fixed; width: 100%; }
.ws-table th { background: #f5f3ff; color: #4c1d95; font-weight: bold; padding: 7pt 10pt; text-align: left; border-bottom: 2pt solid #c4b5fd; }
.ws-table td { padding: 7pt 10pt; border-bottom: 1pt solid #e2e8f0; vertical-align: top; }
.ws-row-num { color: #7c3aed; font-weight: bold; width: 36pt; }
.ws-action { color: #1e1b4b; }
.ws-when { background: #fef9c3; width: 140pt; min-width: 140pt; }
.ws-done { width: 48pt; }
.ws-check { display: inline-block; width: 14pt; height: 14pt; border: 2pt solid #7c3aed; border-radius: 3pt; }
.ws-note { font-size: 8pt; color: #6b7280; font-style: italic; margin-top: 6pt; }
"""
""

_SKIP_SECTION_HEADINGS = frozenset({"table of contents", "contents", "toc"})
_META_SECTION_HEADINGS = frozenset(
    {"summary", "action steps", "product summary", "conclusion", "next steps"}
)
_PROMPT_PREFIXES = (
    "create a", "design a", "generate a", "make a", "illustrate", "show a realistic",
)


def _e(value: Any) -> str:
    return html.escape(str(value or ""))


def _norm_heading(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _looks_like_prompt(text: str) -> bool:
    return looks_like_prompt(text)


def _rich_infographic_html(title: str, caption: str = "") -> str:
    """Title-aware styled visual cards when no generated image exists."""
    t = _norm_heading(title)
    if "title formula" in t:
        body = (
            '<div class="pdf-info-card formula-card">'
            '<div class="pdf-formula-row">'
            '<span class="pdf-formula-part">Main Keyword</span>'
            '<span class="pdf-formula-sep">+</span>'
            '<span class="pdf-formula-part">Style Descriptor</span>'
            '<span class="pdf-formula-sep">+</span>'
            '<span class="pdf-formula-part">Buyer Benefit</span>'
            "</div>"
            '<div class="pdf-formula-note">Strong Etsy title structure</div>'
            "</div>"
        )
    elif "one view" in t or "optimization in one" in t:
        body = (
            '<table class="pdf-principles" width="100%" cellpadding="0" cellspacing="6">'
            "<tr>"
            '<td><b>Find</b><br/>Keywords &amp; tags</td>'
            '<td><b>Convert</b><br/>Photos &amp; copy</td>'
            '<td><b>Improve</b><br/>Measure &amp; refine</td>'
            "</tr></table>"
        )
    elif "high-trust" in t or "listing visual" in t:
        body = (
            '<div class="pdf-listing-mock">'
            '<table width="100%" cellpadding="0" cellspacing="0">'
            "<tr>"
            '<td class="pdf-listing-img" width="80" valign="top">&nbsp;</td>'
            '<td valign="top" style="padding-left:10pt;">'
            '<div class="pdf-listing-title">Handmade Personalized Bookmark -- Custom Name Gift</div>'
            '<div class="pdf-listing-stars">★★★★★ <span class="pdf-listing-meta">(128 reviews)</span></div>'
            '<div class="pdf-listing-meta">In 12 carts · 48 sold this week</div>'
            '<div class="pdf-listing-price">$24.00</div>'
            "</td></tr></table>"
            '<div class="pdf-listing-ship">✓ Free shipping · ✓ Ready to ship in 1-3 days · ✓ Gift wrapping available</div>'
            '<div class="pdf-listing-trust">★ Top Rated Seller</div>'
            '<div class="pdf-listing-cta">Add to cart</div>'
            "</div>"
        )
    elif "roadmap" in t or "ebook roadmap" in t:
        body = (
            '<table class="pdf-principles" width="100%" cellpadding="4" cellspacing="4">'
            "<tr>"
            '<td><b>1</b><br/>Strategy</td>'
            '<td><b>2</b><br/>Titles</td>'
            '<td><b>3</b><br/>Convert</td>'
            "</tr></table>"
        )
    elif "ai model categor" in t or "model type" in t or "types of ai" in t:
        cats = [
            ("Language Models", "Best for text, Q&amp;A, summarization, drafting, and code help."),
            ("Image Models", "Best for visuals, product mockups, ads, and creative concepts."),
            ("Code Models", "Best for debugging, code generation, and technical workflows."),
            ("Multimodal Models", "Best when the task uses text, images, audio, or documents together."),
            ("Embedding Models", "Best for search, recommendations, and RAG retrieval."),
        ]
        rows = "".join(
            f'<tr><td style="font-weight:bold;color:#312e81;padding:6pt 8pt;">{_e(name)}</td>'
            f'<td style="padding:6pt 8pt;">{_e(desc)}</td></tr>'
            for name, desc in cats
        )
        body = (
            '<table class="pdf-table" width="100%" cellpadding="0" cellspacing="0" '
            'style="border-collapse:collapse;margin:8pt 0;">'
            f"{rows}</table>"
        )
    elif "final tip" in t:
        questions = [
            "What task must this model perform?",
            "What data will the model receive?",
            "What quality score is acceptable?",
            "What is the maximum cost per run?",
            "What privacy or risk rule must be checked before launch?",
        ]
        items = "".join(
            f'<tr><td style="padding:6pt 8pt;vertical-align:top;">'
            f'<b style="color:#312e81;">{i}.</b></td>'
            f'<td style="padding:6pt 8pt;">{_e(q)}</td></tr>'
            for i, q in enumerate(questions, 1)
        )
        body = (
            '<table class="pdf-table" width="100%" cellpadding="0" cellspacing="0" '
            'style="border-collapse:collapse;margin:8pt 0;">'
            f"{items}</table>"
        )
    else:
        body = (
            f'<div class="pdf-info-card">'
            f'<div class="pdf-formula-note">{_e(title or "Visual summary")}</div>'
            "</div>"
        )
    return body


def _cover_mockup_html() -> str:
    card = (
        '<td width="33%" class="cover-mini-card" valign="top">'
        '<div class="cover-mini-img"></div>'
        '<div class="cover-mini-title">{title}</div>'
        '<div class="cover-mini-tag">{tag}</div>'
        "</td>"
    )
    cards = (
        card.format(title="Top Seller", tag="handmade · 4.9★")
        + card.format(title="Trending", tag="digital download")
        + card.format(title="Optimized", tag="SEO tags")
    )
    return (
        '<div class="cover-mockup">'
        '<table class="cover-browser" width="100%" cellpadding="0" cellspacing="0">'
        '<tr><td class="cover-browser-bar">'
        '<span class="cover-browser-dots">● ● ●</span>Etsy Marketplace Preview'
        "</td></tr>"
        '<tr><td class="cover-browser-body">'
        '<div class="cover-search">Search optimized Etsy listings, tags &amp; titles...</div>'
        f'<table class="cover-cards-row" width="100%" cellpadding="0" cellspacing="0"><tr>{cards}</tr></table>'
        '<div class="cover-checklist">Title · Tags · Photos · Description · Pricing</div>'
        '<div class="cover-analytics">Clicks · Favorites · Conversions · Search visibility</div>'
        "</td></tr></table></div>"
    )


def _visual_card_html(title: str, caption: str = "", icon: str = "") -> str:
    return _rich_infographic_html(title, caption)


def _chart_html_css(cfg: dict) -> str:
    """HTML/table charts -- xhtml2pdf renders these reliably (unlike SVG text)."""
    labels = cfg.get("labels") or []
    values = [float(v) for v in (cfg.get("values") or [])]
    kind = str(cfg.get("kind") or "bar").lower()
    if not labels or not values:
        return _visual_card_html(cfg.get("title") or "Chart", "Data visualization")
    n = min(len(labels), len(values))
    labels, values = labels[:n], values[:n]

    if kind in ("pie", "doughnut") and n >= 2:
        total = sum(values) or 1.0
        colors = ["#7c3aed", "#0d9488", "#d97706", "#2563eb", "#db2777"]
        cells = []
        for i, (lbl, val) in enumerate(zip(labels, values)):
            pct = int(round(100 * val / total))
            bg = colors[i % len(colors)]
            cells.append(
                f'<td class="pdf-pie-seg" bgcolor="{bg}" style="background-color:{bg};" width="{pct}%">'
                f'<div class="pdf-pie-lbl">{_e(lbl)}</div>'
                f'<div class="pdf-pie-pct">{pct}%</div></td>'
            )
        return (
            '<table class="pdf-pie-chart" width="100%" cellpadding="0" cellspacing="0">'
            f'<tr>{"".join(cells)}</tr></table>'
        )

    max_val = max(values) or 1.0
    chart_title = str(cfg.get("title") or "")
    is_performance = "performance signal" in _norm_heading(chart_title)
    colors = ["#7c3aed", "#0d9488", "#d97706", "#2563eb", "#db2777"]
    bar_cells = []
    col_w = max(24, int(100 / max(len(labels), 1)))
    for i, (lbl, val) in enumerate(zip(labels, values)):
        color = colors[i % len(colors)]
        h = max(22, int(64 * val / max_val))
        if is_performance and max_val == min(values):
            h = 36 + i * 10
        bar_cells.append(
            '<td class="pdf-bar-cell" align="center" valign="bottom" '
            f'width="{col_w}%">'
            f'<div class="pdf-bar-num">{_e(_fmt_num(val))}</div>'
            '<table align="center" cellpadding="0" cellspacing="0" width="28">'
            f'<tr><td class="pdf-bar-fill" bgcolor="{color}" height="{h}" width="22">&nbsp;</td></tr>'
            "</table>"
            f'<div class="pdf-bar-lbl">{_e(str(lbl)[:20])}</div>'
            "</td>"
        )
    plot_row = (
        '<table class="pdf-bar-chart" width="100%" cellpadding="0" cellspacing="0">'
        f'<tr>{"".join(bar_cells)}</tr>'
        f'<tr><td class="pdf-bar-baseline" colspan="{len(bar_cells)}">&nbsp;</td></tr>'
        "</table>"
    )
    if is_performance:
        return (
            '<div class="pdf-bar-chart-wrap">'
            f'{plot_row}</div>'
        )
    return plot_row


def _fmt_num(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.1f}"


def _mermaid_flow_html(code: str, title: str, caption: str) -> str:
    nodes = re.findall(r"\[([^\]]+)\]", str(code or ""))
    nodes = [n.strip() for n in nodes if n.strip()][:6]
    if not nodes:
        return _rich_infographic_html(title or "Diagram", caption)
    rows = []
    for i, node in enumerate(nodes):
        if i:
            rows.append('<tr><td class="pdf-flow-arrow-cell">&#9660;</td></tr>')
        rows.append(
            f'<tr><td class="pdf-flow-box-cell" align="center">'
            f'<table width="90%" align="center" cellpadding="8" cellspacing="0">'
            f'<tr><td bgcolor="#ede9fe" class="pdf-flow-box">{_e(node)}</td></tr>'
            f"</table></td></tr>"
        )
    flow = (
        '<table class="pdf-flow-diagram" width="100%" align="center" cellpadding="0" cellspacing="0">'
        f'{"".join(rows)}</table>'
    )
    return flow


def _cover_page_html(
    title: str, subtitle: str, author: str, product_type: str = "Ebook"
) -> str:
    sub = f'<p class="cover-subtitle">{_e(subtitle)}</p>' if subtitle else ""
    auth = f'<p class="cover-author">{_e(author)}</p>' if author else ""
    inner = (
        '<div class="cover-top">'
        f'<div class="cover-type">{_e(product_type)}</div>'
        '<div class="cover-rule"></div>'
        f'<h1 class="cover-title">{_e(title or "Untitled Product")}</h1>'
        f"{sub}{auth}"
        "</div>"
    )
    # Only show Etsy marketplace mockup for non-ebook products
    if product_type.lower() != "ebook":
        inner += _cover_mockup_html()
    return (
        '<section class="pdf-page cover-page">'
        '<table class="cover-shell" width="100%" cellpadding="0" cellspacing="0">'
        f'<tr><td bgcolor="#0f766e">{inner}</td></tr>'
        "</table></section>"
    )


def _full_page_cover_from_file(path: str) -> str:
    """Embed a local cover photograph as a full-page PDF image."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return _cover_page_html("", "", "")
    if len(raw) < 32:
        return _cover_page_html("", "", "")
    suffix = os.path.splitext(path)[1].lower()
    mime = "image/jpeg" if suffix in {".jpg", ".jpeg"} else "image/png"
    uri = f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")
    return (
        '<section class="pdf-page cover-page cda-cover-full-page">'
        f'<img src="{uri}" alt="Cover" '
        # Letter-page dimensions: the full-bleed page template (margin 0)
        # lets the artwork reach the trim edge instead of sitting in a frame.
        'style="width:612pt;height:792pt;display:block;margin:0;padding:0;" />'
        "</section>"
    )


def _full_page_cover_pdf_html(package_id: str, pending: bool = False) -> str:
    """Render a full-page image cover from the on-disk PNG.
    
    When pending=True, renders a placeholder (used while the image is being generated).
    """
    src = pdf_image_data_uri(package_id, "cover")
    if not src and not pending:
        return _cover_page_html("", "", "")
    if src:
        return (
            '<section class="pdf-page cover-page cda-cover-full-page">'
            f'<img src="{src}" alt="Cover" '
            'style="width:612pt;height:792pt;display:block;margin:0;padding:0;" />'
            "</section>"
        )
    # Pending placeholder
    return (
        '<section class="pdf-page cover-page cda-cover-full-page">'
        '<div style="width:100%;height:8.5in;background:#312e81;display:flex;'
        'align-items:center;justify-content:center;">'
        '<p style="color:#c7d2fe;font-size:14pt;text-align:center;">'
        "Cover image is being generated…"
        "</p></div></section>"
    )


def _inside_title_page_html(
    title: str, subtitle: str, summary: str | None, author: str
) -> str:
    sub = f'<p class="title-sub">{_e(subtitle)}</p>' if subtitle else ""
    sum_block = ""
    if summary and str(summary).strip() and not _looks_like_markdown_source(str(summary)):
        sum_block = f'<p class="summary-lead">{_e(str(summary).strip())}</p>'
    auth = f'<p class="title-sub">by {_e(author)}</p>' if author else ""
    disclaimer = (
        '<p class="title-disclaimer">For educational and informational purposes only. '
        "No warranty is made regarding results from applying this material.</p>"
    )
    return (
        '<section class="pdf-page title-page">'
        f'<h1 class="title-main">{_e(title)}</h1>'
        f"{sub}{auth}{sum_block}{disclaimer}"
        "</section>"
    )


def _toc_entries_from_titles(titles: list[str]) -> list[tuple[str, str]]:
    return [(title, f"chapter-{idx + 1}") for idx, title in enumerate(titles)]


def _toc_page_html(
    entries: list[tuple[str, str]] | list[tuple[str, str, int | str]],
) -> str:
    """Render TOC with optional internal links and page numbers.

    Each entry is (title, anchor) or (title, anchor, page_number).
    """
    if not entries:
        return ""
    rows = []
    for entry in entries:
        title = entry[0]
        page_num = entry[2] if len(entry) > 2 else ""
        page_cell = (
            f'<td style="width:36pt;text-align:right;color:#64748b;">{_e(str(page_num))}</td>'
            if page_num not in ("", None)
            else '<td style="width:36pt;"></td>'
        )
        rows.append(
            "<tr>"
            f'<td style="padding:6pt 0;border-bottom:1pt solid #e2e8f0;font-size:11pt;">'
            f"<b>{_e(title)}</b></td>"
            f"{page_cell}</tr>"
        )
    return (
        '<section class="pdf-page toc-page">'
        "<h2>Table of Contents</h2>"
        '<table width="100%" cellpadding="0" cellspacing="0">'
        f'{"".join(rows)}</table>'
        "</section>"
    )


def _summary_page_html(summary: str) -> str:
    text = summary if isinstance(summary, str) else str(summary)
    if _looks_like_markdown_source(text):
        return ""
    blocks = "".join(
        f"<p>{_e(para.strip())}</p>"
        for para in re.split(r"\n\s*\n", text.strip())
        if para.strip()
    )
    if not blocks.strip():
        return ""
    return (
        '<section class="pdf-page summary-page">'
        f"<h2>Summary</h2>{blocks}"
        "</section>"
    )


def _append_summary_if_needed(parts: list[str], summary: str | None, has_summary: bool) -> bool:
    if has_summary or not summary:
        return has_summary
    html = _summary_page_html(str(summary))
    if html:
        parts.append(html)
        return True
    return False


def _resolve_image_src(src: str) -> str:
    src = str(src or "").strip()
    match = re.match(r"^/download/([a-f0-9]{32})/([^?#]+)", src)
    if match:
        path = os.path.join(EXPORTS_DIR, match.group(1), match.group(2))
        if os.path.isfile(path):
            return "file:///" + os.path.abspath(path).replace("\\", "/")
    return ""



def _strip_embedded_captions(html_fragment: str) -> str:
    if not html_fragment or not html_fragment.strip():
        return html_fragment
    wrapper = BeautifulSoup(f"<wrap>{html_fragment}</wrap>", "html.parser")
    wrap = wrapper.find("wrap")
    if not wrap:
        return html_fragment
    for cap in wrap.select(".va-caption"):
        cap.decompose()
    return wrap.decode_contents()


def _visual_aid_meta(aid: Tag) -> tuple[str, str]:
    title_el = aid.select_one(".va-title")
    cap_el = aid.select_one(".va-caption")
    title = title_el.get_text(strip=True) if title_el else "Visual"
    caption = cap_el.get_text(strip=True) if cap_el else ""
    if _looks_like_prompt(caption):
        caption = ""
    return title, safe_caption(caption)


def _visual_aid_type(aid: Tag | None) -> str:
    if not aid:
        return "infographic"
    classes = " ".join(aid.get("class") or [])
    if "stock-photo" in classes or "stock_photo" in classes:
        return "stock photo"
    return "infographic"


def _embed_local_pdf_image(path: str) -> str:
    """Compressed JPEG data URI, skipping near-duplicate photographs already used."""
    from services.ebook_pdf_images import jpeg_data_uri_from_path, is_near_duplicate

    if not path or not os.path.isfile(path):
        return ""
    try:
        uri, phash, _digest = jpeg_data_uri_from_path(path)
    except Exception:
        return ""
    if is_near_duplicate(phash, _PDF_IMAGE_HASHES):
        return ""
    _PDF_IMAGE_HASHES.append(phash)
    return uri


def _resolve_pdf_image_block(img_wrap: Tag) -> str:
    """Embed a compressed local PNG/JPEG or return a polished fallback — never raw prompts."""
    img = img_wrap.find("img", class_="va-img")
    vid = str(img_wrap.get("data-vid") or (img.get("data-vid") if img else "") or "")
    src = str(img.get("src") if img else "")
    pkg = package_id_from_url(src)
    aid = img_wrap.find_parent(class_="visual-aid")
    title, caption = _visual_aid_meta(aid) if aid else ("Image", "")
    atype = _visual_aid_type(aid)

    local_path = image_asset_path(pkg, vid) if pkg and vid else ""
    if local_path:
        data_uri = _embed_local_pdf_image(local_path)
        if not data_uri:
            if aid:
                aid["data-skip-pdf"] = "1"
            return ""
    else:
        data_uri = pdf_image_data_uri(pkg, vid) if pkg and vid else ""
    if data_uri:
        return (
            f'<img class="pdf-visual-img" src="{data_uri}" alt="{_e(title)}" width="420" '
            'style="max-width:100%;max-height:2.75in;display:block;margin:4pt auto 6pt;" />'
        )
    return pdf_image_fallback_html({"title": title, "caption": caption, "type": atype})


def _tag_pdf_visual_images(inner: str) -> str:
    """Add keep-together class to images inside visual blocks."""
    if not inner or "<img" not in inner:
        return inner
    soup = BeautifulSoup(inner, "html.parser")
    for img in soup.find_all("img"):
        classes = img.get("class") or []
        if isinstance(classes, str):
            classes = classes.split()
        if "pdf-visual-img" not in classes:
            classes.append("pdf-visual-img")
        img["class"] = classes
        if not img.get("width"):
            img["width"] = "420"
        style = str(img.get("style") or "")
        if "max-height" not in style:
            img["style"] = (style + ";max-height:2.75in;").lstrip(";")
    return soup.decode_contents() if hasattr(soup, "decode_contents") else str(soup)


def _pdf_visual_block_html(title: str, inner: str, caption: str) -> str:
    """Single keep-together unit: title + visual + caption (xhtml2pdf table wrapper)."""
    title = (title or "").strip()
    caption = (caption or "").strip()
    if caption and title and caption.casefold() == title.casefold():
        caption = ""
    cap = (
        f'<p class="va-caption pdf-visual-caption">{_e(caption)}</p>'
        if caption and not _looks_like_prompt(caption)
        else ""
    )
    title_html = f'<div class="pdf-visual-title">{_e(title)}</div>' if title else ""
    body = _tag_pdf_visual_images(inner)
    return (
        '<table class="pdf-visual-keep" width="100%" cellpadding="0" cellspacing="0">'
        "<tr><td>"
        '<table class="pdf-visual-frame" width="100%" cellpadding="0" cellspacing="0">'
        '<tr><td class="pdf-visual-block">'
        f"{title_html}"
        f'<div class="pdf-visual-body">{body}</div>'
        f"{cap}"
        "</td></tr></table>"
        "</td></tr></table>"
    )


def _wrap_loose_visual_blocks(soup: BeautifulSoup) -> None:
    """Re-wrap legacy div.pdf-visual-block nodes that are not already in a keep table."""
    for block in list(soup.find_all("div", class_="pdf-visual-block")):
        if block.find_parent(class_="pdf-visual-keep"):
            continue
        title_el = block.select_one(".pdf-visual-title")
        title = title_el.get_text(strip=True) if title_el else "Visual"
        if title_el:
            title_el.extract()
        cap_el = block.select_one(".va-caption, .pdf-visual-caption")
        caption = cap_el.get_text(strip=True) if cap_el else ""
        if cap_el:
            cap_el.extract()
        inner = block.decode_contents()
        wrapped = BeautifulSoup(_pdf_visual_block_html(title, inner, caption), "html.parser")
        block.replace_with(wrapped)


def _compact_visual_aids(soup: BeautifulSoup) -> None:
    """Replace preview visual-aid chrome with a single PDF-friendly keep-together block."""
    for aid in list(soup.find_all(class_="visual-aid")):
        if aid.get("data-skip-pdf"):
            aid.decompose()
            continue
        title, caption = _visual_aid_meta(aid)
        classes = " ".join(aid.get("class") or [])
        is_photo = "stock-photo" in classes or "stock_photo" in classes or "va-photo" in classes
        if is_photo:
            # One label under the photograph — never title + identical caption.
            label = caption or title
            title, caption = "", label
        content_el = aid.select_one(".va-content")
        if content_el:
            inner = _strip_embedded_captions(content_el.decode_contents())
        else:
            clone = BeautifulSoup(str(aid), "html.parser").find(class_="visual-aid")
            for tag in clone.select(".va-label, .va-title, .va-caption"):
                tag.decompose()
            inner = _strip_embedded_captions(clone.decode_contents() if clone else "")
        if is_photo and "<img" not in inner:
            aid.decompose()
            continue
        block = BeautifulSoup(_pdf_visual_block_html(title, inner, caption), "html.parser")
        aid.replace_with(block)
    _wrap_loose_visual_blocks(soup)


def _wrap_as_pdf_table(tag: Tag, *, table_class: str, cell_class: str) -> None:
    """Force a block onto its own line in xhtml2pdf via a 1-cell table."""
    if not isinstance(tag, Tag) or tag.find_parent("table", class_=table_class):
        return
    table_html = (
        f'<table class="{table_class}" width="100%" cellpadding="0" cellspacing="0">'
        f'<tr><td class="{cell_class}"></td></tr></table>'
    )
    table = BeautifulSoup(table_html, "html.parser").table
    td = table.find("td")
    tag.replace_with(table)
    td.append(tag)


def _blockify_pdf_flow(soup: BeautifulSoup) -> None:
    """Force paragraphs and lists onto block lines. Headings stay as real blocks
    so xhtml2pdf does not stack heading tables on top of the following paragraph.
    """
    skip_parents = {"pdf-visual-keep", "pdf-h3-keep", "pdf-p-keep", "pdf-list-keep", "pdf-li-keep", "pdf-callout"}
    for tag in list(soup.find_all("p")):
        parent_table = tag.find_parent("table")
        parent_class = " ".join(parent_table.get("class") or []) if parent_table else ""
        if any(item in parent_class for item in skip_parents):
            continue
        if tag.find_parent(class_="pdf-callout"):
            continue
        _wrap_as_pdf_table(tag, table_class="pdf-p-keep", cell_class="pdf-p-cell")
    for tag in list(soup.find_all("li")):
        parent_table = tag.find_parent("table")
        parent_class = " ".join(parent_table.get("class") or []) if parent_table else ""
        if "pdf-li-keep" in parent_class:
            continue
        _wrap_as_pdf_table(tag, table_class="pdf-li-keep", cell_class="pdf-li-cell")
    for tag in list(soup.find_all(["ul", "ol"])):
        parent_table = tag.find_parent("table")
        parent_class = " ".join(parent_table.get("class") or []) if parent_table else ""
        if any(item in parent_class for item in skip_parents):
            continue
        _wrap_as_pdf_table(tag, table_class="pdf-list-keep", cell_class="pdf-list-cell")


_MD_INLINE_LEAK_RE = re.compile(r"\[([^\]]{1,120})\]\([^)]*\)")
_MD_HEADING_LEAK_RE = re.compile(r"(?m)^#{1,6}\s+")
_CALLOUT_HEADING_RE = re.compile(
    r"^(try this|example scenario|your starting point|a simple buying plan|a weekly care routine)",
    re.I,
)


def _strip_markdown_source_tokens(soup: BeautifulSoup) -> None:
    """Keep link labels, drop raw markdown anchors that escaped the HTML pipeline."""
    for node in list(soup.find_all(string=True)):
        if not isinstance(node, NavigableString):
            continue
        text = str(node)
        if "](" not in text and "#" not in text[:3]:
            if not _MD_HEADING_LEAK_RE.search(text) and "```" not in text:
                continue
        cleaned = _MD_INLINE_LEAK_RE.sub(r"\1", text)
        cleaned = _MD_HEADING_LEAK_RE.sub("", cleaned)
        cleaned = cleaned.replace("```", "")
        if cleaned != text:
            node.replace_with(cleaned)


def _looks_like_markdown_source(text: str) -> bool:
    sample = str(text or "")
    if re.search(r"\]\(#", sample):
        return True
    if re.search(r"\[(?:\d+\.\s*)?[^\]]+\]\([^)]+\)", sample):
        return True
    if re.search(r"(?m)^#{1,6}\s+\S", sample):
        return True
    return False


def _wrap_action_callouts(soup: BeautifulSoup) -> None:
    """Give recurring action/example headings a callout so pages are not walls of type."""
    for heading in list(soup.find_all(["h3", "h4"])):
        label = heading.get_text(" ", strip=True)
        if not _CALLOUT_HEADING_RE.search(label):
            continue
        if heading.find_parent(class_="pdf-callout"):
            continue
        wrapper = soup.new_tag("table")
        wrapper["class"] = ["pdf-callout"]
        wrapper["width"] = "100%"
        wrapper["cellpadding"] = "0"
        wrapper["cellspacing"] = "0"
        tr = soup.new_tag("tr")
        td = soup.new_tag("td")
        td["class"] = ["pdf-callout-cell"]
        wrapper.append(tr)
        tr.append(td)
        heading.insert_before(wrapper)
        td.append(heading.extract())
        sibling = wrapper.next_sibling
        moved = 0
        while sibling is not None and moved < 6:
            nxt = sibling.next_sibling
            if isinstance(sibling, NavigableString) and not str(sibling).strip():
                sibling = nxt
                continue
            if getattr(sibling, "name", None) in {"h2", "h3", "h4"}:
                break
            td.append(sibling.extract())
            moved += 1
            sibling = nxt


def _prepare_pdf_content(node: Tag | BeautifulSoup | str) -> str:
    """Sanitize preview HTML for PDF: no prompts, SVG charts, styled cards."""
    if isinstance(node, str):
        clone = BeautifulSoup(node, "html.parser")
    else:
        clone = BeautifulSoup(str(node), "html.parser")

    for tag in clone(["script", "noscript", "iframe", "video", "audio", "link", "style"]):
        tag.decompose()
    for foot in clone.select(".page-foot, .va-img-spinner, .va-img-note"):
        foot.decompose()
    for note in clone.select(".va-fb-caption"):
        if _looks_like_prompt(note.get_text()):
            note.decompose()

    for wrap in clone.find_all(class_="va-chart-wrap"):
        if wrap.find("canvas", class_="va-chart-canvas"):
            for static in wrap.select(".va-chart-static"):
                static.decompose()

    for flow in clone.find_all(class_="va-flow-static"):
        nodes = []
        for step in flow.select(".va-flow-step"):
            text = re.sub(r"^\d+\s*", "", step.get_text(" ", strip=True))
            if text:
                nodes.append(text)
        parent = flow.find_parent(class_="visual-aid")
        title, caption = _visual_aid_meta(parent) if parent else ("Diagram", "")
        fake_code = " ".join(f"[{n}]" for n in nodes)
        flow.replace_with(
            BeautifulSoup(_mermaid_flow_html(fake_code, title, caption), "html.parser")
        )

    for canvas in clone.find_all("canvas"):
        label, caption = "Chart", ""
        parent = canvas.find_parent(class_="visual-aid")
        if parent:
            label, caption = _visual_aid_meta(parent)
        try:
            cfg = json.loads(canvas.get("data-chart") or "{}")
            cfg["title"] = cfg.get("title") or label
            replacement = BeautifulSoup(_chart_html_css(cfg), "html.parser")
        except (json.JSONDecodeError, TypeError, ValueError):
            replacement = BeautifulSoup(_rich_infographic_html(label, caption), "html.parser")
        canvas.replace_with(replacement)

    for pre in clone.find_all("pre", class_=re.compile(r"mermaid")):
        parent = pre.find_parent(class_="visual-aid")
        title, caption = _visual_aid_meta(parent) if parent else ("Diagram", "")
        code = pre.get_text("\n", strip=True)
        replacement = BeautifulSoup(_mermaid_flow_html(code, title, caption), "html.parser")
        pre.replace_with(replacement)

    for ph in clone.find_all(class_=re.compile(r"va-(chart|diagram)-placeholder")):
        parent = ph.find_parent(class_="visual-aid")
        title, caption = _visual_aid_meta(parent) if parent else ("Visual", "")
        ph.replace_with(
            BeautifulSoup(_rich_infographic_html(title, caption), "html.parser")
        )

    for img_wrap in clone.find_all(class_="va-image"):
        replacement = BeautifulSoup(_resolve_pdf_image_block(img_wrap), "html.parser")
        img_wrap.replace_with(replacement)

    for img in clone.find_all("img", class_="va-img"):
        parent = img.find_parent(class_="va-image")
        if parent:
            continue
        vid = str(img.get("data-vid") or "")
        src = str(img.get("src") or "")
        pkg = package_id_from_url(src)
        aid = img.find_parent(class_="visual-aid")
        title, caption = _visual_aid_meta(aid) if aid else ("Image", "")
        local_path = image_asset_path(pkg, vid) if pkg and vid else ""
        data_uri = _embed_local_pdf_image(local_path) if local_path else (
            pdf_image_data_uri(pkg, vid) if pkg and vid else ""
        )
        if local_path and not data_uri:
            if aid:
                aid["data-skip-pdf"] = "1"
            img.decompose()
            continue
        if data_uri:
            img["src"] = data_uri
            img["width"] = "420"
            classes = img.get("class") or []
            if isinstance(classes, str):
                classes = classes.split()
            if "pdf-visual-img" not in classes:
                classes.append("pdf-visual-img")
            img["class"] = classes
        else:
            atype = _visual_aid_type(aid)
            img.replace_with(
                BeautifulSoup(
                    pdf_image_fallback_html({"title": title, "caption": caption, "type": atype}),
                    "html.parser",
                )
            )

    for fb in clone.find_all(class_=re.compile(r"va-img-fallback|va-fb-card")):
        aid = fb.find_parent(class_="visual-aid")
        if not aid or aid.find_parent(class_="va-image"):
            continue
        title, caption = _visual_aid_meta(aid)
        atype = _visual_aid_type(aid)
        fb.replace_with(
            BeautifulSoup(
                pdf_image_fallback_html({"title": title, "caption": caption, "type": atype}),
                "html.parser",
            )
        )

    for a in clone.find_all("a"):
        href = str(a.get("href") or "").strip()
        if href.startswith("#"):
            continue
        a.replace_with(NavigableString(a.get_text(" ", strip=True)))

    _strip_markdown_source_tokens(clone)
    _wrap_action_callouts(clone)

    html_out = clone.decode_contents() if hasattr(clone, "decode_contents") else str(clone)
    html_out = fix_inline_hyphen_lists_html(html_out)

    clone2 = BeautifulSoup(html_out, "html.parser")
    for aid in clone2.find_all(class_="visual-aid"):
        for body in aid.select(".va-body"):
            if _looks_like_prompt(body.get_text()):
                body.decompose()
    _compact_visual_aids(clone2)
    _wrap_loose_visual_blocks(clone2)
    _blockify_pdf_flow(clone2)

    return clone2.decode_contents() if hasattr(clone2, "decode_contents") else html_out


def _sheet_body_html(sheet: Tag) -> str:
    """Extract inner content from a preview sheet, dropping web-only chrome."""
    clone = BeautifulSoup(str(sheet), "html.parser")
    section = clone.find("section") or clone
    for foot in section.select(".page-foot"):
        foot.decompose()
    inner_parts: list[str] = []
    for child in section.children:
        if isinstance(child, NavigableString) and not str(child).strip():
            continue
        inner_parts.append(str(child))
    return _prepare_pdf_content("".join(inner_parts))


def _section_heading(section: Tag) -> str:
    for tag in section.find_all(["h1", "h2", "h3"], recursive=False):
        return tag.get_text(" ", strip=True)
    heading = section.find(["h1", "h2", "h3"])
    return heading.get_text(" ", strip=True) if heading else ""


def _is_publishing_preview(soup: BeautifulSoup) -> bool:
    return bool(soup.select_one("section.page.cover, .page.cover"))


def _is_visual_preview(soup: BeautifulSoup) -> bool:
    return bool(soup.select_one("section.sheet.cover, .sheet.cover"))


def _extract_publishing_pages(soup: BeautifulSoup, summary: str | None) -> tuple[str, bool]:
    book = soup.select_one(".book") or soup.find("body")
    if not book:
        return "", False

    parts: list[str] = []
    has_summary = False
    for page in book.select("section.page"):
        cls = " ".join(page.get("class") or [])
        heading = _section_heading(page)
        if _norm_heading(heading) == "product summary":
            has_summary = True
        body = _prepare_pdf_content(page)
        parts.append(f'<section class="pdf-page {cls}">{body}</section>')

    if summary and not has_summary:
        html = _summary_page_html(summary)
        if html:
            parts.append(html)
            has_summary = True

    return "".join(parts), has_summary


def _chapter_titles_from_sections(sections: list[Tag]) -> list[str]:
    titles: list[str] = []
    for section in sections:
        heading = _section_heading(section)
        norm = _norm_heading(heading)
        if not heading or norm in _SKIP_SECTION_HEADINGS:
            continue
        if norm in _META_SECTION_HEADINGS:
            continue
        titles.append(heading)
    return titles


def _cover_page_from_design(cover_design: dict | None, title: str, subtitle: str, author: str) -> str:
    '''Use saved Cover Design Agent output for PDF page 1.

    If a cover image PNG exists in the package exports, use it as a full-page
    cover regardless of whether cover_design is present or has a cached pdf_html.
    This prevents silent fall-back to the flat purple cover when the image was
    generated but the cached HTML has not been updated yet.
    '''
    pkg = ""
    if isinstance(cover_design, dict):
        pkg = str(cover_design.get("package_id") or "")
        image_path = str(cover_design.get("image_path") or "").strip()
        if image_path and os.path.isfile(image_path) and os.path.getsize(image_path) > 32:
            return _full_page_cover_from_file(image_path)
        # If the cover design has a proper full-page image HTML already, use it.
        # resolve_cover_pdf_html will detect the on-disk PNG and build the right HTML.
        from services.cover_agent import resolve_cover_pdf_html
        html = resolve_cover_pdf_html(cover_design, pkg)
        # Sanity check: if resolve_cover_pdf_html returned the generic purple shell
        # (no image class), check whether the PNG exists and force the full-page path.
        if 'class="pdf-page cover-page cda-cover-full-page"' in html:
            return html
        # fall through to image check below
    else:
        pkg = ""

    # Even when cover_design is absent or produced a non-image cover,
    # use a full-page image cover if img_cover.png exists on disk.
    if pkg:
        from services.visual_fallback import image_asset_path
        if image_asset_path(pkg, "cover") is not None:
            return _full_page_cover_pdf_html(pkg, pending=False)

    if isinstance(cover_design, dict):
        from services.cover_agent import resolve_cover_pdf_html
        return resolve_cover_pdf_html(cover_design, pkg)
    return _cover_page_html(title, subtitle, author)


def _extract_structured_visual_pages(
    book: Tag,
    *,
    title: str,
    subtitle: str,
    author: str,
    summary: str | None,
    cover_design: dict | None = None,
) -> tuple[str, bool]:
    """Build flat, one-section-per-page PDF layout from ebook preview."""
    parts: list[str] = [_cover_page_from_design(cover_design, title, subtitle, author)]

    has_legal = bool(book.select_one("section.sheet.legal"))
    title_sheet = book.select_one("section.sheet.title-page")
    if title_sheet:
        body = _sheet_body_html(title_sheet)
        disclaimer = ""
        if not has_legal:
            disclaimer = (
                '<p class="title-disclaimer">For educational and informational purposes only. '
                "No warranty is made regarding results from applying this material.</p>"
            )
        parts.append(
            '<section class="pdf-page title-page">'
            f"{body}{disclaimer}"
            "</section>"
        )
    else:
        parts.append(_inside_title_page_html(title, subtitle, None if has_legal else summary, author))

    chapter_titles: list[str] = []
    has_summary = False

    for sheet in book.select("section.sheet"):
        classes = set(sheet.get("class") or [])
        if classes & {"cover", "title-page"}:
            continue
        if "legal" in classes:
            legal_body = _sheet_body_html(sheet)
            if legal_body.strip():
                parts.append(
                    f'<section class="pdf-page legal-page">{legal_body}</section>'
                )
            continue
        if "toc" in classes:
            toc_entries: list[tuple[str, str]] = []
            for li in sheet.select(".toc-list li"):
                link = li.find("a")
                text = link.get_text(strip=True) if link else li.get_text(" ", strip=True)
                if text and _norm_heading(text) not in _SKIP_SECTION_HEADINGS:
                    href = str(link.get("href") or "").strip() if link else ""
                    anchor = href.lstrip("#") if href.startswith("#") else f"chapter-{len(toc_entries) + 1}"
                    toc_entries.append((text, anchor))
            if not toc_entries:
                chapter_titles = _chapter_titles_from_sections(
                    book.select("section.sheet.chapter")
                )
                toc_entries = _toc_entries_from_titles(chapter_titles)
            else:
                chapter_titles = [entry[0] for entry in toc_entries]
            if toc_entries:
                parts.append(_toc_page_html(toc_entries))
            continue

        body = _sheet_body_html(sheet)
        if not body.strip():
            continue

        if "summary" in classes:
            summary_text = BeautifulSoup(body, "html.parser").get_text(" ", strip=True)
            if _looks_like_markdown_source(summary_text):
                continue
            body_only = re.sub(r"^summary\s+", "", summary_text, flags=re.I).strip()
            cleaned_summary = (summary or "").strip()
            chapter_open = ""
            first_ch = book.select_one("section.sheet.chapter")
            if first_ch:
                chapter_open = first_ch.get_text(" ", strip=True)
            def _norm_cmp(value: str) -> str:
                return re.sub(r"\s+", "", value or "").casefold()[:96]
            if cleaned_summary and _norm_cmp(body_only) == _norm_cmp(cleaned_summary):
                has_summary = True  # skip duplicate; do not re-inject product_summary
                continue
            if chapter_open and _norm_cmp(body_only) and _norm_cmp(body_only) in _norm_cmp(chapter_open):
                has_summary = True
                continue
            if len(summary_text) < 80:
                continue
            has_summary = True
            parts.append(
                f'<section class="pdf-page summary-page">{body}</section>'
            )
        elif "action-page" in classes:
            parts.append(
                f'<section class="pdf-page action-page">{body}</section>'
            )
        elif "resources-page" in classes:
            parts.append(
                f'<section class="pdf-page resources-page">{body}</section>'
            )
        elif "chapter" in classes:
            anchor = str(sheet.get("id") or "").strip()
            id_attr = f' id="{_e(anchor)}"' if anchor else ""
            parts.append(
                f'<section class="pdf-page chapter-page"{id_attr}>{body}</section>'
            )

    if summary and not has_summary:
        html = _summary_page_html(summary)
        if html:
            parts.append(html)
            has_summary = True

    # Extract back matter sections (Quick Reference, FAQ, Action Plan)
    # These are div.bm-section elements, not section.sheet elements
    for bm in book.select("div.bm-section"):
        bm_class = " ".join(bm.get("class") or [])
        # Determine page type based on bm-section class
        if "faq-page" in bm_class:
            page_class = "faq-page"
        elif "quick-reference-page" in bm_class:
            page_class = "quick-reference-page"
        elif "worksheet-page" in bm_class:
            page_class = "action-plan-page"
        else:
            page_class = "back-matter-page"
        
        # Get inner HTML
        from bs4 import NavigableString
        inner_parts = []
        for child in bm.children:
            if isinstance(child, NavigableString):
                inner_parts.append(str(child))
            elif child.name not in ("style", "script"):
                inner_parts.append(str(child))
        inner_html = "".join(inner_parts)
        
        if inner_html.strip():
            parts.append(
                f'<section class="pdf-page {page_class}">{inner_html}</section>'
            )

    return "".join(parts), has_summary


def _extract_visual_pages(
    soup: BeautifulSoup,
    *,
    title: str,
    subtitle: str,
    author: str,
    summary: str | None,
    cover_design: dict | None = None,
) -> tuple[str, bool]:
    book = soup.select_one(".book")
    if book and book.select("section.sheet.title-page, section.sheet.toc"):
        return _extract_structured_visual_pages(
            book,
            title=title,
            subtitle=subtitle,
            author=author,
            summary=summary,
            cover_design=cover_design,
        )

    sections = soup.select("section.sheet.chapter")
    chapter_titles = _chapter_titles_from_sections(sections)

    parts = [_cover_page_from_design(cover_design, title, subtitle, author)]
    parts.append(_inside_title_page_html(title, subtitle, summary, author))
    if chapter_titles:
        parts.append(_toc_page_html(_toc_entries_from_titles(chapter_titles)))

    has_summary = False
    for section in sections:
        heading = _section_heading(section)
        norm = _norm_heading(heading)
        if norm in _SKIP_SECTION_HEADINGS:
            continue
        if norm == "product summary":
            has_summary = True
        body_html = _sheet_body_html(section)
        if norm in _META_SECTION_HEADINGS:
            parts.append(
                f'<section class="pdf-page meta-section">{body_html}</section>'
            )
        else:
            parts.append(
                f'<section class="pdf-page chapter-page">{body_html}</section>'
            )

    if summary and not has_summary:
        html = _summary_page_html(summary)
        if html:
            parts.append(html)
            has_summary = True

    return "".join(parts), has_summary


def _build_from_markdown(
    *,
    title: str,
    subtitle: str,
    author: str,
    content: str,
    summary: str | None,
    visual_plan: dict | None,
) -> tuple[str, bool]:
    preamble, chapters = _split_chapters(content or "")
    parts = [_cover_page_html(title, subtitle, author)]
    parts.append(_inside_title_page_html(title, subtitle, summary, author))

    chapter_titles: list[str] = []
    for ch_title, _ in chapters:
        norm = _norm_heading(ch_title)
        if norm in _SKIP_SECTION_HEADINGS or norm in _META_SECTION_HEADINGS:
            continue
        chapter_titles.append(ch_title)
    if chapter_titles:
        parts.append(_toc_page_html(_toc_entries_from_titles(chapter_titles)))

    if preamble.strip():
        norm_preamble = _norm_heading(
            preamble.splitlines()[0].lstrip("#").strip() if preamble else ""
        )
        if norm_preamble not in {_norm_heading(title), "table of contents"}:
            from markdown import markdown

            from services.ebook_package import _sanitize_html

            body = _prepare_pdf_content(
                _sanitize_html(markdown(preamble, extensions=["extra", "sane_lists"]))
            )
            parts.append(
                f'<section class="pdf-page chapter-page">{body}</section>'
            )

    for ch_title, ch_md in chapters:
        norm = _norm_heading(ch_title)
        if norm in _SKIP_SECTION_HEADINGS:
            continue
        from markdown import markdown

        from services.ebook_package import _sanitize_html

        body = _prepare_pdf_content(
            _sanitize_html(markdown(ch_md, extensions=["extra", "sane_lists"]))
        )
        parts.append(
            f'<section class="pdf-page chapter-page">{body}</section>'
        )

    has_summary = any(
        _norm_heading(t) in {"summary", "product summary"} for t, _ in chapters
    )
    if summary and not has_summary:
        html = _summary_page_html(summary)
        if html:
            parts.append(html)
            has_summary = True

    return "".join(parts), has_summary


# Full-bleed cover support. xhtml2pdf applies @page margins to every page, so a
# photo cover always sat inside a white frame. When the body opens with a
# full-bleed cover section, the document starts on a margin-0 page template and
# switches to the normal content template for every following page. Documents
# without such a cover keep the original single-template CSS untouched.
_FULL_BLEED_PAGE_CSS = """
@page { size: letter; margin: 0;
  @frame cover_frame { left: 0pt; top: 0pt; width: 612pt; height: 792pt; } }
@page main { size: letter;
  @frame content_frame { left: 54pt; top: 72pt; width: 504pt; height: 648pt; } }
"""
_MAIN_TEMPLATE_SWITCH = '<pdf:nexttemplate name="main"/>'


def _apply_full_bleed_cover_template(css: str, body_html: str) -> tuple[str, str]:
    if "cda-cover-full-page" not in body_html or _MAIN_TEMPLATE_SWITCH in body_html:
        return css, body_html
    cover_end = body_html.find("</section>")
    if cover_end < 0:
        return css, body_html
    # The switch must be seen before the cover's page-break-after fires, or the
    # page AFTER the title page is the first one to get content margins.
    body_html = body_html[:cover_end] + _MAIN_TEMPLATE_SWITCH + body_html[cover_end:]
    css = re.sub(r"@page\s*\{[^}]*\}", "", css, count=1)
    return _FULL_BLEED_PAGE_CSS + css, body_html


def _wrap_pdf_document(title: str, body_html: str, template_key: str = "", body_class: str = "") -> str:
    if template_key or (body_class or "").startswith("tpl-"):
        css = build_publishing_pdf_css(template_key or body_class.replace("tpl-", ""))
        cls = body_class or (f"tpl-{template_key}" if template_key else "")
    else:
        css = _PDF_CSS
        cls = body_class
    css, body_html = _apply_full_bleed_cover_template(css, body_html)
    class_attr = f' class="{cls}"' if cls else ""
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        f"<!-- PDF-EXPORT-{PDF_EXPORT_VERSION} -->"
        f"<title>{_e(title)}</title><style>{css}</style></head>"
        f"<body{class_attr}>{body_html}</body></html>"
    )


def build_pdf_html(
    *,
    doc_html: str,
    title: str,
    subtitle: str = "",
    author: str = "",
    content: str = "",
    summary: str | None = None,
    visual_plan: dict | None = None,
    preview_source: str = "",
    template_key: str = "",
    cover_design: dict | None = None,
) -> str:
    # Stored summaries can be polluted with raw markdown TOC links (old fallback
    # derivation); every summary render site below receives the cleaned value.
    summary = clean_product_summary(summary) or None
    raw = str(doc_html or "").strip()
    soup = BeautifulSoup(raw, "html.parser") if raw else None
    body_class = ""
    if soup and soup.body:
        body_class = " ".join(soup.body.get("class") or [])
    if not template_key and raw and preview_source != "visual":
        template_key = detect_template_key(raw)

    body = ""
    has_summary = False
    if preview_source == "visual":
        template_key = ""
    if soup and (_is_publishing_preview(soup) or preview_source == "publishing"):
        body, has_summary = _extract_publishing_pages(soup, summary)
    elif soup and (_is_visual_preview(soup) or preview_source == "visual"):
        body, has_summary = _extract_visual_pages(
            soup,
            title=title,
            subtitle=subtitle,
            author=author,
            summary=summary,
            cover_design=cover_design,
        )
    elif content:
        body, has_summary = _build_from_markdown(
            title=title,
            subtitle=subtitle,
            author=author,
            content=content,
            summary=summary,
            visual_plan=visual_plan,
        )
    elif raw:
        body = _prepare_pdf_content(soup.find("body") or soup)
        if summary:
            body += _summary_page_html(summary)
    else:
        body = _cover_page_from_design(cover_design, title, subtitle, author)
        body += _inside_title_page_html(title, subtitle, summary, author)
        if summary:
            body += _summary_page_html(summary)

    if not body.strip():
        body = _cover_page_from_design(cover_design, title, subtitle, author)

    return _wrap_pdf_document(title, body, template_key=template_key, body_class=body_class)


def _strip_letter_spacing_css(html_doc: str) -> str:
    """Remove CSS letter-spacing declarations that corrupt xhtml2pdf glyph advances."""
    return re.sub(
        r"letter-spacing\s*:\s*[^;\"']+;?",
        "",
        html_doc or "",
        flags=re.I,
    )


_LOCAL_PDF_URI_RE = re.compile(
    r"https?://(?:127\.0\.0\.1|localhost)(?::\d+)?|ebook-workspace/|full-preview|file://",
    re.I,
)
_CHAPTER_FRAG_RE = re.compile(r"(?:^#|[#/])(chapter-\d+)\b", re.I)


def _sanitize_pdf_local_link_uris(pdf_bytes: bytes) -> bytes:
    """Convert localhost/file/Flask preview URIs into document-internal chapter jumps.

    Leaves the PDF bytes unchanged when no leaking URIs are present so preview
    identity stays deterministic.
    """
    if not pdf_bytes or not pdf_bytes.startswith(b"%PDF"):
        return pdf_bytes
    try:
        import fitz
    except Exception:
        return pdf_bytes
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        return pdf_bytes
    changed = False
    chapter_pages: dict[str, int] = {}
    try:
        for i, page in enumerate(doc):
            text = page.get_text("text") or ""
            for match in re.finditer(r"Chapter\s+(\d+)", text):
                chapter_pages.setdefault(f"chapter-{match.group(1)}", i)
        for page in doc:
            for link in list(page.get_links() or []):
                uri = str(link.get("uri") or "")
                if not uri:
                    continue
                frag_match = _CHAPTER_FRAG_RE.search(uri)
                leaking = bool(_LOCAL_PDF_URI_RE.search(uri))
                if not leaking and not frag_match:
                    continue
                dest_name = (frag_match.group(1).lower() if frag_match else "")
                dest = chapter_pages.get(dest_name)
                if not leaking and dest is None:
                    continue
                try:
                    page.delete_link(link)
                    if dest is not None:
                        page.insert_link(
                            {
                                "kind": fitz.LINK_GOTO,
                                "from": link.get("from"),
                                "page": dest,
                            }
                        )
                    changed = True
                except Exception:
                    continue
        if not changed:
            return pdf_bytes
        return doc.tobytes()
    finally:
        doc.close()


def _html_to_pdf_xhtml2pdf(html_doc: str) -> bytes:
    from xhtml2pdf import pisa

    from services.ebook_fonts import EBOOK_FONT, ebook_font_face_css, ensure_ebook_fonts, patch_xhtml2pdf_local_ttf

    ensure_ebook_fonts()
    patch_xhtml2pdf_local_ttf()
    html_doc = _strip_letter_spacing_css(html_doc)
    uses_ebook_sans = EBOOK_FONT in html_doc
    face_css = ebook_font_face_css() if uses_ebook_sans else ""
    if face_css and "<style" in html_doc:
        html_doc = html_doc.replace("<style", f"<style>{face_css}</style><style", 1)
    elif face_css and "<head>" in html_doc:
        html_doc = html_doc.replace("<head>", f"<head><style>{face_css}</style>", 1)

    buf = io.BytesIO()
    # Do not force EbookSans onto designed-path HTML (Georgia/Calibri). That
    # substitution wrapped tables and clipped the fixture's last pages.
    default_css = (
        f"body {{ font-family: {EBOOK_FONT}, Helvetica, Arial, sans-serif; }}"
        if uses_ebook_sans
        else None
    )
    result = pisa.CreatePDF(
        html_doc,
        dest=buf,
        encoding="utf-8",
        default_css=default_css,
    )
    if result.err:
        raise RuntimeError("xhtml2pdf conversion failed")
    data = buf.getvalue()
    if not data:
        raise RuntimeError("xhtml2pdf produced empty PDF")
    return data


def _apply_pdf_metadata(
    pdf_bytes: bytes,
    *,
    title: str,
    author: str = "",
    subject: str = "",
    keywords: str = "",
) -> bytes:
    """Set Title/Author/Subject/Keywords/Creator from project values."""
    try:
        from pypdf import PdfReader, PdfWriter
    except Exception:
        return pdf_bytes
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        writer.add_metadata(
            {
                "/Title": title or "Ebook",
                "/Author": author or "Anonymous Author",
        "/Subject": subject or title or "Ebook",
                "/Keywords": keywords or "ebook",
                "/Creator": "Ebook Generator",
                "/Producer": "Ebook Generator",
            }
        )
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()
    except Exception:
        return pdf_bytes


def _find_chapter_pages(pdf_bytes: bytes, titles: list[str]) -> dict[str, int]:
    """Map chapter title -> 1-based page number using text search."""
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    found: dict[str, int] = {}
    # Skip cover + any early TOC pages when matching chapter openings
    start_page = 0
    for i in range(min(doc.page_count, 6)):
        text = (doc.load_page(i).get_text("text") or "").lower()
        if "table of contents" in text:
            start_page = i + 1
            break
    # Preload page heads for faster matching
    page_heads: list[str] = []
    page_full: list[str] = []
    for i in range(doc.page_count):
        text = doc.load_page(i).get_text("text") or ""
        # Normalize whitespace so wrapped titles still match
        norm = re.sub(r"\s+", " ", text).strip().lower()
        page_full.append(norm)
        page_heads.append(norm[:500])

    for title in titles:
        needle = re.sub(r"\s+", " ", (title or "").strip()).lower()
        if len(needle) < 6:
            continue
        words = needle.split()
        probes = [needle]
        if len(words) >= 4:
            probes.append(" ".join(words[:4]))
            probes.append(" ".join(words[:6]))
        probes.append(needle[:50].strip())
        probes = [p for p in probes if len(p) >= 6]
        matched = False
        for i in range(start_page, doc.page_count):
            head = page_heads[i]
            if any(p in head for p in probes):
                found[title] = i + 1
                matched = True
                break
        if matched:
            continue
        for i in range(start_page, doc.page_count):
            if any(p in page_full[i] for p in probes):
                found[title] = i + 1
                break
    doc.close()
    return found


def _rebuild_toc_with_page_numbers(
    pdf_bytes: bytes,
    chapter_titles: list[str],
) -> bytes:
    """Replace the TOC page with one that includes correct page numbers."""
    if not chapter_titles:
        return pdf_bytes
    try:
        import fitz
        from pypdf import PdfReader, PdfWriter
    except Exception:
        return pdf_bytes

    pages_map = _find_chapter_pages(pdf_bytes, chapter_titles)
    if not pages_map:
        return pdf_bytes

    # Build a one-page TOC PDF
    entries = [
        (t, f"chapter-{i+1}", pages_map.get(t, ""))
        for i, t in enumerate(chapter_titles)
    ]
    toc_html = _wrap_pdf_document(
        "Table of Contents",
        _toc_page_html(entries),
    )
    try:
        toc_pdf = _html_to_pdf_xhtml2pdf(toc_html)
    except Exception:
        return pdf_bytes

    reader = PdfReader(io.BytesIO(pdf_bytes))
    toc_reader = PdfReader(io.BytesIO(toc_pdf))
    writer = PdfWriter()

    # Locate existing TOC page
    toc_idx = None
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    for i in range(min(doc.page_count, 8)):
        text = (doc.load_page(i).get_text("text") or "").lower()
        # Never replace a copyright/disclaimer sheet that happened to mention TOC.
        if "table of contents" in text and "copyright" not in text:
            toc_idx = i
            break
    doc.close()
    if toc_idx is None:
        return pdf_bytes

    for i, page in enumerate(reader.pages):
        if i == toc_idx and toc_reader.pages:
            writer.add_page(toc_reader.pages[0])
        else:
            writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _count_blank_pages(pdf_bytes: bytes) -> int:
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    blank = 0
    for i in range(doc.page_count):
        text = (doc.load_page(i).get_text("text") or "").strip()
        if len(text) < 12:
            blank += 1
        elif (
            len(text) < 180
            and "for educational and informational purposes only" in text.lower()
            and "copyright" not in text.lower()
            and "table of contents" not in text.lower()
        ):
            blank += 1
    doc.close()
    return blank


def _remove_accidental_blank_pages(pdf_bytes: bytes) -> bytes:
    """Drop interior pages that are essentially empty (keep cover even if sparse)."""
    try:
        import fitz
        from pypdf import PdfReader, PdfWriter
    except Exception:
        return pdf_bytes
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    keep: list[int] = []
    for i in range(doc.page_count):
        if i == 0:
            keep.append(i)
            continue
        text = (doc.load_page(i).get_text("text") or "").strip()
        low = text.lower()
        if len(text) >= 12 and not (
            len(text) < 180
            and "for educational and informational purposes only" in low
            and "copyright" not in low
            and "table of contents" not in low
        ):
            keep.append(i)
    doc.close()
    if len(keep) == PdfReader(io.BytesIO(pdf_bytes)).get_num_pages():
        return pdf_bytes
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    for i in keep:
        writer.add_page(reader.pages[i])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _extract_pdf_sections(pdf_html: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(pdf_html, "html.parser")
    sections: list[tuple[str, str]] = []
    for section in soup.find_all("section"):
        heading = _section_heading(section) or section.get("class", ["Section"])[0].title()
        text = section.get_text("\n", strip=True)
        if text:
            sections.append((heading, text))
    return sections


def _build_pdf_reportlab(*, title: str, subtitle: str, author: str, sections: list[tuple[str, str]]) -> bytes:
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.85 * inch,
        rightMargin=0.85 * inch,
        topMargin=0.85 * inch,
        bottomMargin=0.85 * inch,
        title=title or "Product",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ProductTitle", parent=styles["Title"], alignment=TA_CENTER, fontSize=24, leading=28, spaceAfter=12
    )
    subtitle_style = ParagraphStyle(
        "ProductSubtitle", parent=styles["Normal"], alignment=TA_CENTER, fontSize=13, textColor="#6b7280", spaceAfter=8
    )
    h2_style = ParagraphStyle(
        "SectionHeading", parent=styles["Heading2"], fontSize=16, spaceBefore=14, spaceAfter=8
    )
    body_style = ParagraphStyle(
        "ProductBody", parent=styles["BodyText"], fontSize=10, leading=14, spaceAfter=6
    )

    story: list[Any] = []
    story.append(Spacer(1, 1.5 * inch))
    story.append(Paragraph(_e(title or "Untitled Product"), title_style))
    if subtitle:
        story.append(Paragraph(_e(subtitle), subtitle_style))
    if author:
        story.append(Paragraph(f"by {_e(author)}", subtitle_style))
    story.append(PageBreak())

    for heading, text in sections:
        if _norm_heading(heading) in {"cover-page", "cover page"}:
            continue
        if heading:
            story.append(Paragraph(_e(heading), h2_style))
        for para in re.split(r"\n\s*\n", text):
            chunk = para.strip()
            if chunk and chunk != heading:
                story.append(Paragraph(_e(chunk).replace("\n", "<br/>"), body_style))

    doc.build(story)
    data = buf.getvalue()
    if not data:
        raise RuntimeError("reportlab produced empty PDF")
    return data


def generate_product_pdf(
    *,
    doc_html: str,
    title: str,
    subtitle: str = "",
    author: str = "",
    content: str = "",
    summary: str | None = None,
    visual_plan: dict | None = None,
    preview_source: str = "",
    template_key: str = "",
    cover_design: dict | None = None,
    subject: str = "",
    keywords: str = "",
    topic: str = "",
    audience: str = "",
) -> bytes:
    from services.ebook_cover_local import generate_local_cover_pdf_bytes
    from services.ebook_fonts import ensure_ebook_fonts
    from services.ebook_package import _split_chapters
    from services.ebook_pdf_images import full_bleed_cover_pdf_bytes, stamp_running_matter

    ensure_ebook_fonts()
    _reset_pdf_image_dedupe()

    pdf_html = build_pdf_html(
        doc_html=doc_html,
        title=title,
        subtitle=subtitle,
        author=author,
        content=content,
        summary=summary,
        visual_plan=visual_plan,
        preview_source=preview_source,
        template_key=template_key,
        cover_design=cover_design,
    )

    img_path = ""
    if isinstance(cover_design, dict):
        img_path = str(cover_design.get("image_path") or "")
        if not img_path and cover_design.get("package_id"):
            cand = os.path.join(EXPORTS_DIR, str(cover_design["package_id"]), "img_cover.png")
            if os.path.isfile(cand):
                img_path = cand
    has_real_png_cover = bool(img_path and os.path.isfile(img_path) and os.path.getsize(img_path) > 20_000)
    use_local_cover = not has_real_png_cover

    local_cover_path = ""
    if isinstance(cover_design, dict):
        local_cover_path = str(cover_design.get("local_cover_pdf") or "")
        if not local_cover_path and cover_design.get("package_id"):
            candidate = os.path.join(
                EXPORTS_DIR, str(cover_design["package_id"]), "cover_local.pdf"
            )
            if os.path.isfile(candidate):
                local_cover_path = candidate

    visual_locked = preview_source == "visual" or (
        isinstance(preview_source, str) and "sheet cover" in preview_source[:5000]
    )

    def _body_pdf_from_html(html_doc: str) -> bytes:
        try:
            return _html_to_pdf_xhtml2pdf(html_doc)
        except Exception:
            if visual_locked:
                raise
            sections = _extract_pdf_sections(html_doc)
            return _build_pdf_reportlab(
                title=title, subtitle=subtitle, author=author, sections=sections
            )

    def _strip_html_cover(html_doc: str) -> str:
        soup = BeautifulSoup(html_doc, "html.parser")
        for sec in soup.select("section.cover-page, section.cda-cover-full-page"):
            sec.decompose()
        text = str(soup)
        # Keep a single main-template switch at the start of the body. The
        # HTML cover (and the switch that lived inside it) is gone; without
        # this, xhtml2pdf keeps the margin-0 cover @page for every interior
        # sheet and stamps collide with body text.
        text = text.replace(_MAIN_TEMPLATE_SWITCH, "")
        text = re.sub(r"(<body[^>]*>)", r"\1" + _MAIN_TEMPLATE_SWITCH, text, count=1)
        return text

    if has_real_png_cover:
        body_html = _strip_html_cover(pdf_html)
        body_pdf = _body_pdf_from_html(body_html)
        try:
            cover_pdf = full_bleed_cover_pdf_bytes(img_path)
        except Exception:
            cover_pdf = b""
        if cover_pdf.startswith(b"%PDF"):
            pdf_bytes = _prepend_pdf_bytes(cover_pdf, body_pdf)
        else:
            pdf_bytes = body_pdf
    elif use_local_cover:
        stripped_html = _strip_html_cover(pdf_html)
        body_pdf = _body_pdf_from_html(stripped_html)
        body_pdf = _strip_cover_section_from_pdf(body_pdf)
        if local_cover_path and os.path.isfile(local_cover_path):
            with open(local_cover_path, "rb") as fh:
                rl_cover = fh.read()
        elif isinstance(cover_design, dict) and cover_design.get("workflow") == "photo_backed":
            raise ValueError("Photo-backed cover PDF is missing. Export cannot reconstruct the cover.")
        else:
            rl_cover = generate_local_cover_pdf_bytes(
                title,
                subtitle,
                author=author or "Anonymous Author",
                topic=topic or title,
                audience=audience,
            )
        pdf_bytes = _prepend_pdf_bytes(rl_cover, body_pdf)
    else:
        pdf_bytes = _body_pdf_from_html(pdf_html)

    chapter_titles: list[str] = []
    if content:
        _intro, chapters = _split_chapters(content)
        chapter_titles = [
            c[0]
            for c in chapters
            if c and c[0] and _norm_heading(c[0]) not in _SKIP_SECTION_HEADINGS
        ]
    if chapter_titles:
        pdf_bytes = _remove_accidental_blank_pages(pdf_bytes)
        pdf_bytes = _rebuild_toc_with_page_numbers(pdf_bytes, chapter_titles)
    else:
        pdf_bytes = _remove_accidental_blank_pages(pdf_bytes)
    pdf_bytes = stamp_running_matter(pdf_bytes, title=title, author=author)

    meta_subject = subject or subtitle or title or "Ebook"
    meta_keywords = keywords or ", ".join(
        p for p in [topic, audience, "ebook"] if p
    )
    pdf_bytes = _apply_pdf_metadata(
        pdf_bytes,
        title=title or "Ebook",
        author=author or "Anonymous Author",
        subject=meta_subject,
        keywords=meta_keywords,
    )

    _log_validation(pdf_bytes)
    return pdf_bytes
