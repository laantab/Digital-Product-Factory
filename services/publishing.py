"""Publishing Studio.

Takes a saved Product Project (ebook, product, or product plan) and turns it into
a polished, Designrr-style ebook preview rendered as a self-contained HTML
document. The AI normalizes the source content into a clean book structure; the
HTML is then rendered deterministically using one of several visual templates.

Only an in-app HTML preview is produced here. PDF/DOCX export is intentionally
out of scope for this module.
"""
import html
import re
from datetime import datetime, timezone
from string import Template
from urllib.parse import urlparse

from ai_client import chat_json
from services.ebook_package import interleave_aids_in_html, VISUAL_SCRIPTS, render_aid_html

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
# Each template controls cover layout, fonts, headings, chapter titles, colors,
# spacing, tip/action box styling, visual-aid placement, footer and page-number
# style. Shared structure comes from a tokenized base stylesheet; each template
# adds signature flourishes via `extra_css`.

TEMPLATES = {
    "clean_business": {
        "name": "Clean Business Guide",
        "desc": "Professional, corporate, serif headings on a crisp white page.",
        "fonts": "Inter:wght@400;600;700&family=Merriweather:wght@400;700",
        "tokens": {
            "f_head": "'Merriweather', Georgia, serif",
            "f_body": "'Inter', system-ui, sans-serif",
            "primary": "#1e293b",
            "accent": "#2563eb",
            "ink": "#0f172a",
            "muted": "#64748b",
            "bg": "#ffffff",
            "surface": "#f1f5f9",
            "line": "#e2e8f0",
            "cover_bg": "#ffffff",
            "cover_ink": "#0f172a",
            "radius": "6px",
        },
        "labels": {"tip": "Pro Tip", "action": "Action Steps", "resource": "Video Resource"},
        "placement": "grouped",
        "extra_css": """
.tpl-clean_business .cover { border-top: 16px solid #2563eb; }
.tpl-clean_business .cover-title { font-size: 44px; letter-spacing: -0.02em; }
.tpl-clean_business .cover-rule { width: 110px; height: 3px; background: #2563eb; }
.tpl-clean_business .toc h2 { border-bottom: 3px solid #2563eb; padding-bottom: 12px; display: inline-block; }
.tpl-clean_business .toc li span:first-child { font-weight: 600; color: #1e293b; }
.tpl-clean_business .chapter-title { border-bottom: 2px solid #e2e8f0; padding-bottom: 12px; margin-bottom: 24px; }
.tpl-clean_business .chapter-num { background: #eff6ff; color: #2563eb; padding: 6px 14px; border-radius: 4px; display: inline-block; margin-bottom: 10px; }
.tpl-clean_business .tip { border-left: 5px solid #2563eb; background: #f8fafc; }
.tpl-clean_business .actions { background: #f8fafc; border-left: 5px solid #1e293b; }
.tpl-clean_business .page-footer .page-num { font-weight: 700; color: #2563eb; }
""",
        "pdf_extra_css": """
.page.cover { background: #ffffff; color: #0f172a; border-top: 14pt solid #2563eb; text-align: center; }
.page.cover .cover-title { color: #0f172a; font-size: 26pt; }
.page.toc h2 { border-bottom: 2pt solid #2563eb; padding-bottom: 8pt; }
.page.chapter .chapter-num { background: #eff6ff; color: #2563eb; padding: 4pt 10pt; font-size: 9pt; }
.tip { border-left: 4pt solid #2563eb; background: #f8fafc; }
.actions { border-left: 4pt solid #1e293b; background: #f8fafc; }
.page-footer .page-num { font-weight: bold; color: #2563eb; }
""",
    },
    "modern_lead_magnet": {
        "name": "Modern Lead Magnet",
        "desc": "Bold gradient cover, punchy sans-serif, rounded accent boxes.",
        "fonts": "Poppins:wght@400;600;700;800",
        "tokens": {
            "f_head": "'Poppins', system-ui, sans-serif",
            "f_body": "'Poppins', system-ui, sans-serif",
            "primary": "#6d28d9",
            "accent": "#db2777",
            "ink": "#1f2937",
            "muted": "#6b7280",
            "bg": "#ffffff",
            "surface": "#f5f3ff",
            "line": "#ede9fe",
            "cover_bg": "linear-gradient(135deg, #6d28d9 0%, #db2777 100%)",
            "cover_ink": "#ffffff",
            "radius": "16px",
        },
        "labels": {"tip": "Quick Win", "action": "Take Action", "resource": "Watch & Learn"},
        "placement": "inline",
        "extra_css": """
.tpl-modern_lead_magnet .cover-title { font-size: 52px; font-weight: 800; text-shadow: 0 2px 18px rgba(0,0,0,0.18); }
.tpl-modern_lead_magnet .cover-badge { background: rgba(255,255,255,0.22); border: 2px solid rgba(255,255,255,0.45); }
.tpl-modern_lead_magnet .cover-rule { background: #ffffff; width: 100px; height: 5px; }
.tpl-modern_lead_magnet .toc h2 { color: #6d28d9; }
.tpl-modern_lead_magnet .toc .toc-num { background: #f5f3ff; padding: 4px 12px; border-radius: 999px; }
.tpl-modern_lead_magnet .chapter-num { background: #f5f3ff; color: #6d28d9; padding: 6px 16px; border-radius: 999px; display: inline-block; font-weight: 800; }
.tpl-modern_lead_magnet .chapter-title { color: #6d28d9; }
.tpl-modern_lead_magnet .tip { background: linear-gradient(135deg, #f5f3ff, #fce7f3); border: 2px solid #ede9fe; }
.tpl-modern_lead_magnet .actions { border: 2px solid #ede9fe; background: #faf5ff; }
.tpl-modern_lead_magnet .cta { background: linear-gradient(135deg, #6d28d9, #db2777); }
""",
        "pdf_extra_css": """
.page.cover { background: #6d28d9; color: #ffffff; text-align: center; }
.page.cover .cover-title, .page.cover .cover-kicker, .page.cover .cover-byline { color: #ffffff; }
.page.cover .cover-badge { background: #7c3aed; color: #ffffff; }
.page.toc .toc-num { color: #db2777; font-weight: bold; }
.page.chapter .chapter-num { color: #6d28d9; font-weight: bold; }
.page.chapter .chapter-title { color: #6d28d9; }
.tip { background: #f5f3ff; border: 1pt solid #ede9fe; }
.actions { background: #faf5ff; border: 1pt solid #ede9fe; }
.cta { background: #6d28d9; color: #ffffff; padding: 14pt; text-align: center; }
""",
    },
    "workbook": {
        "name": "Workbook Style",
        "desc": "Practical, warm tones with check-box action steps and hint boxes.",
        "fonts": "Roboto+Slab:wght@400;700&family=Karla:wght@400;600;700",
        "tokens": {
            "f_head": "'Roboto Slab', serif",
            "f_body": "'Karla', system-ui, sans-serif",
            "primary": "#0f766e",
            "accent": "#d97706",
            "ink": "#1c1917",
            "muted": "#78716c",
            "bg": "#fffdf7",
            "surface": "#f0fdfa",
            "line": "#e7e5e4",
            "cover_bg": "#0f766e",
            "cover_ink": "#ffffff",
            "radius": "10px",
        },
        "labels": {"tip": "Helpful Hint", "action": "Your Turn", "resource": "Watch This"},
        "placement": "inline",
        "extra_css": """
.tpl-workbook .cover { background: #0f766e; }
.tpl-workbook .cover-badge { background: #d97706; border-radius: 12px; }
.tpl-workbook .cover-rule { background: #d97706; }
.tpl-workbook .toc h2 { color: #0f766e; }
.tpl-workbook .chapter-num { color: #d97706; font-weight: 800; letter-spacing: 0.14em; }
.tpl-workbook .chapter-title { color: #0f766e; border-bottom: 2px dashed #d97706; padding-bottom: 10px; }
.tpl-workbook .tip { border: 2px dashed #d97706; background: #fffbeb; }
.tpl-workbook .actions { border: 2px solid #0f766e; background: #f0fdfa; }
.tpl-workbook .actions ol { list-style: none; padding-left: 0; }
.tpl-workbook .actions li { position: relative; padding-left: 34px; margin: 12px 0; }
.tpl-workbook .actions li::before { content: ""; position: absolute; left: 0; top: 3px; width: 18px; height: 18px; border: 2px solid #0f766e; border-radius: 4px; background: #fff; }
""",
        "pdf_extra_css": """
.page.cover { background: #0f766e; color: #ffffff; text-align: center; }
.page.cover .cover-title, .page.cover .cover-kicker, .page.cover .cover-byline { color: #ffffff; }
.page.cover .cover-badge { background: #d97706; color: #ffffff; }
.page.chapter .chapter-title { color: #0f766e; border-bottom: 1pt dashed #d97706; padding-bottom: 8pt; }
.page.chapter .chapter-num { color: #d97706; font-weight: bold; }
.tip { border: 1pt dashed #d97706; background: #fffbeb; }
.actions { border: 1pt solid #0f766e; background: #f0fdfa; }
""",
    },
    "kids_education": {
        "name": "Kids / Education Style",
        "desc": "Playful, bright and rounded with friendly, approachable type.",
        "fonts": "Fredoka:wght@500;600;700&family=Nunito:wght@400;600;700",
        "tokens": {
            "f_head": "'Fredoka', system-ui, sans-serif",
            "f_body": "'Nunito', system-ui, sans-serif",
            "primary": "#2563eb",
            "accent": "#f59e0b",
            "ink": "#1f2937",
            "muted": "#6b7280",
            "bg": "#ffffff",
            "surface": "#fef9c3",
            "line": "#fde68a",
            "cover_bg": "linear-gradient(135deg, #3b82f6 0%, #22c55e 100%)",
            "cover_ink": "#ffffff",
            "radius": "22px",
        },
        "labels": {"tip": "Did You Know?", "action": "Let's Try It", "resource": "Watch & Play"},
        "placement": "inline",
        "extra_css": """
.tpl-kids_education .cover-title { font-size: 50px; font-weight: 800; }
.tpl-kids_education .cover-badge { background: #f59e0b; border-radius: 999px; font-size: 44px; }
.tpl-kids_education .toc h2 { color: #2563eb; }
.tpl-kids_education .toc .toc-num { background: #fef9c3; color: #d97706; padding: 4px 12px; border-radius: 999px; font-weight: 800; }
.tpl-kids_education .chapter-num { color: #2563eb; font-weight: 800; font-size: 14px; }
.tpl-kids_education .chapter-title { color: #2563eb; }
.tpl-kids_education .tip { background: #dcfce7; border: 3px solid #22c55e; border-radius: 18px; }
.tpl-kids_education .actions { background: #dbeafe; border: 3px solid #3b82f6; border-radius: 18px; }
.tpl-kids_education .actions ol { list-style: none; padding-left: 0; counter-reset: step; }
.tpl-kids_education .actions li { position: relative; padding-left: 42px; margin: 12px 0; counter-increment: step; }
.tpl-kids_education .actions li::before { content: counter(step); position: absolute; left: 0; top: -2px; width: 28px; height: 28px; background: #f59e0b; color: #fff; border-radius: 999px; text-align: center; line-height: 28px; font-weight: 800; }
""",
        "pdf_extra_css": """
.page.cover { background: #2563eb; color: #ffffff; text-align: center; }
.page.cover .cover-title, .page.cover .cover-kicker, .page.cover .cover-byline { color: #ffffff; }
.page.cover .cover-badge { background: #f59e0b; color: #ffffff; border-radius: 999px; }
.page.toc .toc-num { color: #d97706; font-weight: bold; }
.page.chapter .chapter-title { color: #2563eb; }
.tip { background: #dcfce7; border: 2pt solid #22c55e; }
.actions { background: #dbeafe; border: 2pt solid #3b82f6; }
""",
    },
    "faith_church": {
        "name": "Faith / Church Guide Style",
        "desc": "Elegant serif with warm gold and burgundy on a soft cream page.",
        "fonts": "Playfair+Display:wght@500;700&family=Lora:wght@400;500;700",
        "tokens": {
            "f_head": "'Playfair Display', Georgia, serif",
            "f_body": "'Lora', Georgia, serif",
            "primary": "#7f1d1d",
            "accent": "#b45309",
            "ink": "#3f2d2d",
            "muted": "#8a7a72",
            "bg": "#fffaf3",
            "surface": "#fdf6ec",
            "line": "#e8dcc8",
            "cover_bg": "#7f1d1d",
            "cover_ink": "#fdf6ec",
            "radius": "4px",
        },
        "labels": {"tip": "Reflection", "action": "Apply This", "resource": "Watch Together"},
        "placement": "grouped",
        "extra_css": """
.tpl-faith_church .cover { background: #7f1d1d; }
.tpl-faith_church .cover-badge { background: #b45309; border-radius: 4px; }
.tpl-faith_church .cover-title { font-size: 46px; font-weight: 500; }
.tpl-faith_church .cover-title::after { content: ""; display: block; width: 90px; height: 3px; background: #b45309; margin: 18px auto 0; }
.tpl-faith_church .toc h2 { font-style: italic; color: #7f1d1d; }
.tpl-faith_church .chapter-title { color: #7f1d1d; }
.tpl-faith_church .chapter-title::after { content: ""; display: block; width: 60px; height: 2px; background: #b45309; margin-top: 12px; }
.tpl-faith_church .chapter-num { color: #b45309; font-style: italic; letter-spacing: 0.08em; }
.tpl-faith_church .tip { font-style: italic; border-left: 5px solid #b45309; background: #fdf6ec; }
.tpl-faith_church .actions { border: 1px solid #e8dcc8; background: #fffaf3; }
.tpl-faith_church .page-footer .footer-brand { color: #7f1d1d; }
""",
        "pdf_extra_css": """
.page.cover { background: #7f1d1d; color: #fdf6ec; text-align: center; }
.page.cover .cover-title, .page.cover .cover-kicker, .page.cover .cover-byline { color: #fdf6ec; }
.page.cover .cover-badge { background: #b45309; color: #ffffff; }
.page.chapter .chapter-title { color: #7f1d1d; }
.page.chapter .chapter-num { color: #b45309; font-style: italic; }
.tip { border-left: 4pt solid #b45309; background: #fdf6ec; font-style: italic; }
.actions { border: 1pt solid #e8dcc8; background: #fffaf3; }
""",
    },
}

_DEFAULT_DISCLAIMER = (
    "The information in this book is provided for general educational purposes "
    "only. While every effort has been made to ensure accuracy, the author and "
    "publisher make no guarantees and accept no liability for any outcomes "
    "resulting from the use of this material."
)


def template_list() -> list[dict]:
    """Lightweight list for the frontend picker."""
    out = []
    for key, tpl in TEMPLATES.items():
        cover = tpl["tokens"]["cover_bg"]
        if "gradient" in str(cover):
            cover = tpl["tokens"]["primary"]
        out.append(
            {
                "id": key,
                "name": tpl["name"],
                "desc": tpl["desc"],
                "accent": tpl["tokens"]["accent"],
                "primary": tpl["tokens"]["primary"],
                "cover": cover,
            }
        )
    return out


def _e(value) -> str:
    return html.escape(str(value or ""))


def _safe_url(url: str) -> str:
    try:
        parsed = urlparse(str(url or ""))
        return url if parsed.scheme in ("http", "https") else ""
    except ValueError:
        return ""


# ---------------------------------------------------------------------------
# Source extraction + AI structuring
# ---------------------------------------------------------------------------

_PUBLISHABLE = {"ebook", "product", "product_plan"}


def _extract_source(project: dict) -> tuple[str, str, str]:
    """Return (title, subtitle, raw_text) for a publishable project."""
    data = project.get("data") or {}
    ptype = project.get("type")
    name = project.get("name") or "Untitled"

    if ptype == "ebook":
        return name, "", str(data.get("ebook") or "")
    if ptype == "product":
        return str(data.get("title") or name), "", str(data.get("content") or "")
    if ptype == "product_plan":
        plan = data.get("plan") or {}
        parts = []
        if plan.get("product_description"):
            parts.append(str(plan["product_description"]))
        if plan.get("product_promise"):
            parts.append("Promise: " + str(plan["product_promise"]))
        if plan.get("main_transformation"):
            parts.append("Transformation: " + str(plan["main_transformation"]))
        if plan.get("outline"):
            parts.append(
                "Outline:\n" + "\n".join(f"- {o}" for o in plan["outline"])
            )
        if plan.get("bonus_ideas"):
            parts.append(
                "Bonuses:\n" + "\n".join(f"- {b}" for b in plan["bonus_ideas"])
            )
        if plan.get("sales_angle"):
            parts.append("Sales angle: " + str(plan["sales_angle"]))
        return (
            str(plan.get("product_title") or name),
            str(plan.get("subtitle") or ""),
            "\n\n".join(parts),
        )

    raise ValueError(
        "This project cannot be published. Choose an Ebook, Product, or "
        "Product Plan project."
    )


def _coerce_book(raw: dict, title_hint: str, subtitle_hint: str) -> dict:
    if not isinstance(raw, dict):
        raw = {}
    chapters = []
    for ch in raw.get("chapters") or []:
        if not isinstance(ch, dict):
            continue
        paragraphs = ch.get("paragraphs")
        if isinstance(paragraphs, str):
            paragraphs = [paragraphs]
        elif not isinstance(paragraphs, list):
            paragraphs = []
        paragraphs = [str(p).strip() for p in paragraphs if str(p).strip()]

        steps = ch.get("action_steps")
        if isinstance(steps, str):
            steps = [steps]
        elif not isinstance(steps, list):
            steps = []
        steps = [str(s).strip() for s in steps if str(s).strip()]

        title = str(ch.get("title") or "").strip()
        if not title and not paragraphs:
            continue
        chapters.append(
            {
                "title": title or "Untitled Chapter",
                "paragraphs": paragraphs,
                "tip": str(ch.get("tip") or "").strip(),
                "action_steps": steps,
            }
        )

    return {
        "title": str(raw.get("title") or title_hint or "Untitled").strip(),
        "subtitle": str(raw.get("subtitle") or subtitle_hint or "").strip(),
        "chapters": chapters,
        "summary": str(raw.get("summary") or "").strip(),
    }


def _structure_book(raw_text: str, title_hint: str, subtitle_hint: str) -> dict:
    raw_text = (raw_text or "").strip()
    if not raw_text:
        raise ValueError("This project has no content to publish yet.")

    raw = chat_json(
        system=(
            "You are a book editor who reorganizes existing draft content into a "
            "clean, structured ebook ready for layout. You preserve the author's "
            "content and wording as much as possible and never invent large "
            "amounts of new material."
        ),
        user=(
            "Reorganize the DRAFT below into a clean ebook structure for a "
            "formatted preview.\n\n"
            f"Suggested title: {title_hint}\n\n"
            f"DRAFT:\n{raw_text[:16000]}\n\n"
            "Return a JSON object with EXACTLY these keys:\n"
            '- "title": string.\n'
            '- "subtitle": string (a short tagline; may be empty).\n'
            '- "chapters": array of objects, each with: "title" (string), '
            '"paragraphs" (array of plain-text paragraph strings with NO markdown '
            'symbols), "tip" (a short helpful tip string, or "" if none fits), '
            '"action_steps" (array of short action-step strings, or []).\n'
            '- "summary": string, a closing summary of 1-3 plain-text '
            "paragraphs separated by blank lines.\n"
            "Rules: Use only the draft's information. Strip all markdown symbols. "
            "Add a tip or action steps only where they fit naturally. Aim for 3-8 "
            "chapters. Do not use emojis. Return only the JSON object."
        ),
        max_completion_tokens=6000,
    )
    book = _coerce_book(raw, title_hint, subtitle_hint)
    if not book["chapters"]:
        raise ValueError("Could not structure this project into chapters.")
    return book


# ---------------------------------------------------------------------------
# Publishing details
# ---------------------------------------------------------------------------

_DETAIL_KEYS = [
    "product_title",
    "subtitle",
    "author_brand",
    "disclaimer",
    "copyright_text",
    "call_to_action",
    "website_contact",
]


def default_details(project: dict) -> dict:
    """Sensible prefilled publishing details for a chosen project."""
    title, subtitle, _ = _extract_source(project)
    year = datetime.now(timezone.utc).year
    return {
        "product_title": title,
        "subtitle": subtitle,
        "author_brand": "",
        "disclaimer": _DEFAULT_DISCLAIMER,
        "copyright_text": f"Copyright {year}. All rights reserved.",
        "call_to_action": "",
        "website_contact": "",
    }


def _clean_details(details: dict, fallback: dict) -> dict:
    details = details or {}
    out = {}
    for key in _DETAIL_KEYS:
        value = details.get(key)
        value = value.strip() if isinstance(value, str) else ""
        out[key] = value or fallback.get(key, "")
    return out


# ---------------------------------------------------------------------------
# Visual aids
# ---------------------------------------------------------------------------


def _aid_from_project(project: dict) -> dict:
    data = project.get("data") or {}
    points = data.get("key_teaching_points")
    if not isinstance(points, list):
        points = []
    return {
        "video_title": str(data.get("video_title") or project.get("name") or "Video resource"),
        "video_url": str(data.get("video_url") or ""),
        "summary": str(data.get("summary") or ""),
        "caption": str(data.get("caption") or ""),
        "resource_note": str(data.get("resource_note") or ""),
        "chapter_placement": str(data.get("chapter_placement") or ""),
        "key_teaching_points": [str(p).strip() for p in points if str(p).strip()],
        "has_qr": bool(data.get("qr_code")),
    }


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

_BASE_CSS = Template(
    """
* { box-sizing: border-box; }
html, body { margin: 0; }
body { background: #e9edf3; font-family: $f_body; color: $ink; }
.book { max-width: 820px; margin: 0 auto; padding: 28px 16px 60px; }
.page {
  background: $bg; border: 1px solid $line; border-radius: $radius;
  margin: 0 0 26px; padding: 56px 58px; min-height: 1040px; position: relative;
  box-shadow: 0 12px 34px rgba(15, 23, 42, 0.10); display: flex; flex-direction: column;
}
.page-body { flex: 1; }
h1, h2, h3, h4 { font-family: $f_head; color: $primary; line-height: 1.22; margin: 0; }
.page p { line-height: 1.78; font-size: 16px; margin: 0 0 16px; }
.cover { background: $cover_bg; color: $cover_ink; align-items: center; justify-content: center; text-align: center; position: relative; overflow: hidden; }
.cover-frame { position: absolute; inset: 26px; border: 2px solid $accent; border-radius: $radius; opacity: 0.5; pointer-events: none; }
.cover-band-top { position: absolute; top: 0; left: 0; right: 0; height: 96px; background: $accent; opacity: 0.14; }
.cover-band-bottom { position: absolute; bottom: 0; left: 0; right: 0; height: 96px; background: $primary; opacity: 0.12; }
.cover-blob { position: absolute; width: 360px; height: 360px; border-radius: 50%; background: $accent; opacity: 0.10; top: -130px; right: -120px; }
.cover-blob.two { width: 280px; height: 280px; background: $primary; opacity: 0.08; top: auto; right: auto; bottom: -110px; left: -90px; }
.cover-stack { position: relative; z-index: 2; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; width: 100%; padding: 0 46px; }
.cover-badge { width: 86px; height: 86px; border-radius: 22px; background: $accent; color: #ffffff; display: flex; align-items: center; justify-content: center; font-family: $f_head; font-size: 40px; font-weight: 800; margin: 0 0 28px; box-shadow: 0 14px 32px rgba(15, 23, 42, 0.20); }
.resources h2 { font-size: 30px; margin-bottom: 18px; }
.cover h1, .cover h2 { color: $cover_ink; }
.cover-kicker { letter-spacing: 0.22em; text-transform: uppercase; font-size: 13px; opacity: 0.85; font-weight: 700; }
.cover-title { font-size: 46px; margin: 14px 0 0; font-weight: 800; line-height: 1.15; }
.cover-rule { width: 88px; height: 4px; background: $accent; border-radius: 999px; margin: 22px auto; }
.cover-subtitle { font-size: 20px; opacity: 0.92; max-width: 82%; line-height: 1.55; margin: 0 auto; }
.cover-byline { margin-top: 30px; font-size: 15px; opacity: 0.9; font-weight: 600; }
.cover-imprint { position: absolute; bottom: 42px; left: 0; right: 0; z-index: 2; font-size: 11px; letter-spacing: 0.2em; text-transform: uppercase; opacity: 0.6; }
.legal h2 { font-size: 26px; margin-bottom: 16px; }
.legal h3 { font-size: 18px; margin-top: 24px; }
.legal p { color: $muted; font-size: 14px; line-height: 1.65; }
.toc h2 { font-size: 30px; margin-bottom: 28px; font-weight: 800; }
.toc ol { list-style: none; padding: 0; margin: 0; }
.toc li { display: flex; justify-content: space-between; align-items: baseline; gap: 14px; padding: 14px 0; border-bottom: 1px dashed $line; font-size: 16px; }
.toc li span:first-child { flex: 1; padding-right: 12px; }
.toc .toc-num { color: $accent; font-weight: 700; font-size: 14px; white-space: nowrap; }
.chapter-num { color: $accent; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; font-size: 13px; margin-bottom: 8px; }
.chapter-title { font-size: 30px; margin: 8px 0 24px; font-weight: 800; line-height: 1.2; }
.box-label { font-family: $f_head; color: $primary; font-weight: 700; font-size: 12px; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.08em; }
.tip { background: $surface; border-radius: $radius; padding: 18px 20px; margin: 22px 0; border-left: 4px solid $accent; }
.tip p { margin: 0; font-size: 15px; line-height: 1.65; }
.actions { border: 1px solid $line; border-radius: $radius; padding: 18px 20px; margin: 22px 0; background: $surface; }
.actions ol { margin: 8px 0 0; padding-left: 22px; }
.actions li { margin: 9px 0; line-height: 1.55; font-size: 15px; }
.resource-box { border: 1px solid $line; border-left: 4px solid $accent; border-radius: $radius; padding: 18px 20px; margin: 22px 0; background: $surface; }
.resource-head { color: $accent; font-weight: 700; font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }
.resource-title { font-family: $f_head; font-weight: 700; color: $primary; font-size: 18px; margin: 4px 0 10px; }
.resource-body { display: flex; gap: 18px; align-items: flex-start; }
.resource-text { flex: 1; }
.resource-text p { font-size: 14px; margin: 0 0 8px; }
.resource-points { margin: 0 0 8px; padding-left: 18px; font-size: 14px; }
.resource-link { color: $accent; word-break: break-all; font-size: 13px; }
.resource-note { color: $muted; font-style: italic; font-size: 13px; }
.qr { text-align: center; }
.qr-box { width: 88px; height: 88px; border: 2px dashed $accent; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-weight: 800; color: $accent; font-family: $f_head; letter-spacing: 0.05em; }
.qr-cap { font-size: 11px; color: $muted; margin-top: 5px; }
.cta { background: $primary; color: #ffffff; border-radius: $radius; padding: 24px 26px; margin-top: 22px; text-align: center; }
.cta .cta-label { text-transform: uppercase; letter-spacing: 0.1em; font-size: 12px; opacity: 0.85; font-weight: 700; }
.cta p { color: #ffffff; margin: 8px 0 0; font-size: 17px; line-height: 1.55; }
.cta a { color: #ffffff; font-weight: 700; }
.page-footer { display: flex; justify-content: space-between; align-items: center; border-top: 1px solid $line; margin-top: 36px; padding-top: 14px; font-size: 12px; color: $muted; }
.page-footer .footer-brand { font-family: $f_head; font-weight: 600; color: $primary; }
.page-footer .page-num { font-variant-numeric: tabular-nums; font-weight: 700; min-width: 24px; text-align: right; }
.visual-aid { border: 1px solid $line; border-radius: $radius; background: $bg; padding: 18px 20px; margin: 24px 0; box-shadow: 0 2px 10px rgba(15,23,42,0.05); }
.visual-aid .va-label { display: inline-block; background: $surface; color: $accent; font-weight: 700; font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; padding: 4px 10px; border-radius: 999px; margin-bottom: 10px; }
.visual-aid .va-title { font-family: $f_head; font-weight: 700; color: $primary; font-size: 17px; margin-bottom: 10px; }
.visual-aid .va-caption { font-size: 13px; font-style: italic; color: $muted; margin-top: 10px; }
.visual-aid .va-table { border-collapse: collapse; width: 100%; font-size: 14px; }
.visual-aid .va-table th, .visual-aid .va-table td { border: 1px solid $line; padding: 8px 10px; text-align: left; }
.visual-aid .va-table th { background: $surface; color: $primary; font-weight: 700; }
.summary h2 { font-size: 28px; margin-bottom: 18px; }
"""
)


def _build_css(template_key: str) -> str:
    tpl = TEMPLATES[template_key]
    base = _BASE_CSS.substitute(tpl["tokens"])
    return base + tpl.get("extra_css", "")


_PDF_BASE_CSS = """
@page { size: letter; margin: 0.7in 0.75in; }
body { margin: 0; font-family: Georgia, 'Times New Roman', serif; color: #1f2937; font-size: 11pt; line-height: 1.68; }
.page { page-break-after: always; page-break-inside: avoid; padding: 0; margin: 0; border: none; box-shadow: none; min-height: 0; background: transparent; }
.page:last-child { page-break-after: auto; }
.page.cover { page-break-after: always; text-align: center; padding-top: 2in; min-height: 8in; }
.cover-stack { text-align: center; }
.cover-badge { width: 64pt; height: 64pt; line-height: 64pt; border-radius: 12pt; font-size: 28pt; font-weight: bold; margin: 0 auto 18pt; display: block; text-align: center; }
.cover-kicker { font-size: 9pt; text-transform: uppercase; letter-spacing: 1.5pt; margin-bottom: 10pt; }
.cover-title { font-size: 26pt; font-weight: bold; line-height: 1.2; margin: 10pt 0; }
.cover-rule { width: 72pt; height: 3pt; margin: 14pt auto; }
.cover-subtitle { font-size: 13pt; line-height: 1.5; margin: 0 auto 16pt; max-width: 85%; }
.cover-byline { font-size: 11pt; margin-top: 20pt; }
.cover-imprint { font-size: 8pt; text-transform: uppercase; letter-spacing: 1.5pt; margin-top: 40pt; opacity: 0.7; }
.page.toc h2 { font-size: 20pt; margin: 0 0 16pt; }
.page.toc ol { list-style: none; margin: 0; padding: 0; }
.page.toc li { padding: 8pt 0; border-bottom: 1pt dashed #d1d5db; font-size: 11pt; }
.page.toc .toc-num { float: right; font-weight: bold; }
.page.chapter { page-break-before: always; }
.chapter-num { font-size: 9pt; text-transform: uppercase; letter-spacing: 1pt; font-weight: bold; margin-bottom: 8pt; }
.chapter-title { font-size: 18pt; font-weight: bold; margin: 0 0 14pt; line-height: 1.25; }
.page p { margin: 0 0 10pt; font-size: 11pt; line-height: 1.68; }
h3 { font-size: 13pt; margin: 14pt 0 8pt; }
.tip, .actions, .resource-box, .visual-aid { padding: 10pt 12pt; margin: 12pt 0; border: 1pt solid #d1d5db; }
.box-label, .resource-head, .visual-aid .va-label { font-size: 8pt; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5pt; margin-bottom: 6pt; }
.actions ol, .actions ul { margin: 6pt 0 0 16pt; }
.actions li { margin: 5pt 0; }
.page-footer { margin-top: 24pt; padding-top: 8pt; border-top: 1pt solid #e5e7eb; font-size: 9pt; color: #6b7280; }
.page-footer .page-num { float: right; font-weight: bold; }
.page.summary h2, .page.legal h2 { font-size: 18pt; margin-bottom: 12pt; }
img { max-width: 100%; height: auto; }
.va-chart-placeholder, .va-diagram-placeholder { border: 1pt dashed #9ca3af; padding: 10pt; text-align: center; color: #6b7280; font-style: italic; }
.cta { padding: 14pt; margin-top: 14pt; text-align: center; border-radius: 6pt; }
.cta p, .cta a { color: #ffffff; }
"""


def build_publishing_pdf_css(template_key: str | None = None) -> str:
    """PDF-safe stylesheet that mirrors the selected Publishing Studio template."""
    key = template_key if template_key in TEMPLATES else "clean_business"
    tpl = TEMPLATES[key]
    tokens = tpl["tokens"]
    accent = tokens["accent"]
    primary = tokens["primary"]
    css = (
        _PDF_BASE_CSS
        + f"\nbody {{ color: {tokens['ink']}; }}\n"
        f"h1, h2, h3, .chapter-title {{ color: {primary}; }}\n"
        f".chapter-num, .toc .toc-num, .box-label, .resource-head {{ color: {accent}; }}\n"
        f".tip, .actions, .resource-box, .visual-aid {{ border-left: 4pt solid {accent}; background: {tokens['surface']}; }}\n"
    )
    css += tpl.get("pdf_extra_css", "")
    return css


def detect_template_key(html_doc: str) -> str:
    """Read tpl-* class from saved publishing preview HTML."""
    match = re.search(r'tpl-([a-z_]+)', str(html_doc or ""))
    if match and match.group(1) in TEMPLATES:
        return match.group(1)
    return ""


def _footer(details: dict, page_num: int) -> str:
    brand = _e(details.get("website_contact") or details.get("author_brand"))
    return (
        '<div class="page-footer">'
        f'<span class="footer-brand">{brand}</span>'
        f'<span class="page-num">{page_num}</span>'
        "</div>"
    )


def _paragraphs(text_or_list) -> str:
    if isinstance(text_or_list, list):
        items = text_or_list
    else:
        items = [p for p in str(text_or_list or "").split("\n\n")]
    return "".join(f"<p>{_e(p.strip())}</p>" for p in items if str(p).strip())


def _tip_html(tip: str, label: str) -> str:
    if not tip:
        return ""
    return (
        f'<div class="tip"><div class="box-label">{_e(label)}</div>'
        f"<p>{_e(tip)}</p></div>"
    )


def _actions_html(steps: list, label: str) -> str:
    if not steps:
        return ""
    items = "".join(f"<li>{_e(s)}</li>" for s in steps)
    return (
        f'<div class="actions"><div class="box-label">{_e(label)}</div>'
        f"<ol>{items}</ol></div>"
    )


def _resource_html(aid: dict, label: str) -> str:
    points = ""
    if aid.get("key_teaching_points"):
        lis = "".join(f"<li>{_e(p)}</li>" for p in aid["key_teaching_points"])
        points = f'<ul class="resource-points">{lis}</ul>'
    body_text = aid.get("summary") or aid.get("caption") or ""
    note = (
        f'<p class="resource-note">{_e(aid["resource_note"])}</p>'
        if aid.get("resource_note")
        else ""
    )
    safe = _safe_url(aid.get("video_url"))
    link = (
        f'<a class="resource-link" href="{_e(safe)}" target="_blank" '
        f'rel="noopener">{_e(aid.get("video_url"))}</a>'
        if safe
        else ""
    )
    return (
        '<div class="resource-box">'
        f'<div class="resource-head">{_e(label)}</div>'
        f'<div class="resource-title">{_e(aid.get("video_title"))}</div>'
        '<div class="resource-body">'
        '<div class="resource-text">'
        f"{f'<p>{_e(body_text)}</p>' if body_text else ''}"
        f"{points}{link}{note}"
        "</div>"
        '<div class="qr">'
        '<div class="qr-box">QR</div>'
        '<div class="qr-cap">Scan to watch</div>'
        "</div>"
        "</div></div>"
    )


def _source_visuals(project: dict) -> tuple[list, str]:
    """Pull the saved ebook visual plan (charts/tables/diagrams/boxes/images)."""
    data = (project or {}).get("data") or {}
    vp = data.get("visual_plan") or {}
    chapters = vp.get("chapters") or []
    package_id = str(data.get("package_id") or "")
    return chapters, package_id


def _norm_chapter(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _map_source_aids(book_chapters: list, src_chapters: list) -> dict:
    """Attach saved ebook visuals to book chapters (title match first, then index,
    with any leftovers appended to the last chapter so nothing is dropped)."""
    result: dict[int, list] = {i: [] for i in range(len(book_chapters))}
    if not book_chapters or not src_chapters:
        if book_chapters:
            for sc in src_chapters:
                result[0].extend(sc.get("aids") or [])
        return result
    title_index: dict[str, int] = {}
    for i, bc in enumerate(book_chapters):
        title_index.setdefault(_norm_chapter(bc.get("title")), i)
    last = len(book_chapters) - 1
    for si, sc in enumerate(src_chapters):
        aids = sc.get("aids") or []
        if not aids:
            continue
        bi = title_index.get(_norm_chapter(sc.get("chapter")))
        if bi is None:
            bi = si if si < len(book_chapters) else last
        result[bi].extend(aids)
    return result


def _render_html(
    book: dict,
    template_key: str,
    details: dict,
    aids: list,
    ebook_aids: dict | None = None,
    package_id: str = "",
) -> str:
    tpl = TEMPLATES[template_key]
    labels = tpl["labels"]
    placement = tpl["placement"]
    css = _build_css(template_key)
    chapters = book["chapters"]

    # Distribute visual aids across chapters when the template places them inline.
    inline_map: dict[int, list] = {}
    grouped: list = []
    if aids:
        if placement == "inline" and chapters:
            for i, aid in enumerate(aids):
                inline_map.setdefault(i % len(chapters), []).append(aid)
        else:
            grouped = list(aids)

    pages: list[str] = []
    page_num = 0

    title = details.get("product_title") or book["title"]
    subtitle = details.get("subtitle") or book["subtitle"]
    author = details.get("author_brand")

    # Cover (no footer / page number).
    cover_kicker_text = author or "Digital Guide"
    cover_subtitle = (
        f'<p class="cover-subtitle">{_e(subtitle)}</p>' if subtitle else ""
    )
    cover_byline = f'<div class="cover-byline">by {_e(author)}</div>' if author else ""
    badge_char = (re.sub(r"\s", "", title)[:1] or "E").upper()
    pages.append(
        '<section class="page cover">'
        '<div class="cover-band-top"></div><div class="cover-band-bottom"></div>'
        '<div class="cover-blob"></div><div class="cover-blob two"></div>'
        '<div class="cover-frame"></div>'
        '<div class="page-body cover-stack">'
        f'<div class="cover-badge">{_e(badge_char)}</div>'
        f'<div class="cover-kicker">{_e(cover_kicker_text)}</div>'
        f'<h1 class="cover-title">{_e(title)}</h1>'
        '<div class="cover-rule"></div>'
        f"{cover_subtitle}"
        f"{cover_byline}"
        "</div>"
        '<div class="cover-imprint">Digital Product Factory</div>'
        "</section>"
    )

    # Copyright / disclaimer.
    page_num += 2  # cover counts as page 1
    pages.append(
        '<section class="page legal"><div class="page-body">'
        "<h2>Copyright</h2>"
        f'<p>{_e(details.get("copyright_text"))}</p>'
        "<h3>Disclaimer</h3>"
        f"{_paragraphs(details.get('disclaimer'))}"
        f"</div>{_footer(details, page_num)}</section>"
    )

    # Table of contents.
    page_num += 1
    toc_items = "".join(
        f'<li><span>{_e(ch["title"])}</span>'
        f'<span class="toc-num">Chapter {i + 1}</span></li>'
        for i, ch in enumerate(chapters)
    )
    pages.append(
        '<section class="page toc"><div class="page-body">'
        "<h2>Table of Contents</h2>"
        f"<ol>{toc_items}</ol>"
        f"</div>{_footer(details, page_num)}</section>"
    )

    # Chapters.
    for i, ch in enumerate(chapters):
        page_num += 1
        inline_aids = "".join(
            _resource_html(a, labels["resource"]) for a in inline_map.get(i, [])
        )
        ebook_aids_list = (ebook_aids or {}).get(i, [])
        para_html = _paragraphs(ch["paragraphs"])
        body_html = interleave_aids_in_html(para_html, ebook_aids_list, package_id)
        pages.append(
            '<section class="page chapter"><div class="page-body">'
            f'<div class="chapter-num">Chapter {i + 1}</div>'
            f'<h2 class="chapter-title">{_e(ch["title"])}</h2>'
            f"{body_html}"
            f"{_tip_html(ch['tip'], labels['tip'])}"
            f"{_actions_html(ch['action_steps'], labels['action'])}"
            f"{inline_aids}"
            f"</div>{_footer(details, page_num)}</section>"
        )

    # Grouped video resources page.
    if grouped:
        page_num += 1
        boxes = "".join(_resource_html(a, labels["resource"]) for a in grouped)
        pages.append(
            '<section class="page resources"><div class="page-body">'
            "<h2>Bonus Video Resources</h2>"
            f"{boxes}"
            f"</div>{_footer(details, page_num)}</section>"
        )

    # Summary + call to action.
    page_num += 1
    cta = ""
    if details.get("call_to_action") or details.get("website_contact"):
        safe = _safe_url(details.get("website_contact"))
        link = (
            f'<p><a href="{_e(safe)}" target="_blank" rel="noopener">'
            f'{_e(details.get("website_contact"))}</a></p>'
            if safe
            else (
                f"<p>{_e(details.get('website_contact'))}</p>"
                if details.get("website_contact")
                else ""
            )
        )
        cta_text = (
            f"<p>{_e(details.get('call_to_action'))}</p>"
            if details.get("call_to_action")
            else ""
        )
        cta = (
            '<div class="cta"><div class="cta-label">Next Step</div>'
            f"{cta_text}{link}</div>"
        )
    pages.append(
        '<section class="page summary"><div class="page-body">'
        "<h2>Summary</h2>"
        f"{_paragraphs(book['summary']) or '<p>Thank you for reading.</p>'}"
        f"{cta}"
        f"</div>{_footer(details, page_num)}</section>"
    )

    scripts = VISUAL_SCRIPTS if any((ebook_aids or {}).values()) else ""
    fonts_href = f"https://fonts.googleapis.com/css2?family={tpl['fonts']}&display=swap"
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<link rel="preconnect" href="https://fonts.googleapis.com">'
        f'<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        f'<link rel="stylesheet" href="{fonts_href}">'
        f"<style>{css}</style></head>"
        f'<body class="tpl-{template_key}"><div class="book">{"".join(pages)}</div>'
        f"{scripts}"
        "</body></html>"
    )


def build_publishing_preview(
    project: dict, template_key: str, details: dict, aid_projects: list
) -> dict:
    """Orchestrate: extract source, structure with AI, render templated HTML."""
    if template_key not in TEMPLATES:
        raise ValueError("Please choose a valid ebook template.")

    title_hint, subtitle_hint, raw_text = _extract_source(project)
    book = _structure_book(raw_text, title_hint, subtitle_hint)

    fallback = default_details(project)
    clean = _clean_details(details, fallback)

    aids = [_aid_from_project(p) for p in aid_projects if p]
    src_chapters, package_id = _source_visuals(project)
    ebook_aids = _map_source_aids(book["chapters"], src_chapters)
    html_doc = _render_html(book, template_key, clean, aids, ebook_aids, package_id)

    return {
        "source_project_id": project.get("id"),
        "source_name": project.get("name"),
        "template": template_key,
        "details": clean,
        "visual_aid_ids": [p.get("id") for p in aid_projects if p],
        "book": book,
        "preview_html": html_doc,
    }
