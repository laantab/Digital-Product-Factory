"""Premium full-page cover templates when AI artwork is unavailable."""
from __future__ import annotations

import html
import re
from typing import Any

from services.cover_agent import (
    _font_stack,
    _title_size_class,
    cover_subtitle_font_px,
    cover_title_font_px,
    normalize_text_position,
    text_layer_position_css,
)


def _e(value: Any) -> str:
    return html.escape(str(value or ""))


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower()).strip()


def resolve_cover_theme(cover: dict) -> dict[str, str]:
    """Topic-aware palette and mood for template covers."""
    blob = _norm(
        " ".join(
            [
                str(cover.get("title") or ""),
                str(cover.get("subtitle") or ""),
                str(cover.get("author") or ""),
                str(cover.get("cover_prompt") or ""),
                str(cover.get("image_prompt") or ""),
                str((cover.get("topic_analysis") or {}).get("reason") or ""),
            ]
        )
    )
    palette = cover.get("color_palette") if isinstance(cover.get("color_palette"), dict) else {}
    accent = str(palette.get("accent") or "#d4af37")
    text = str(palette.get("text") or "#ffffff")

    if any(k in blob for k in ("black history", "african american", "civil rights", "harlem")):
        return {
            "key": "black_history",
            "bg_top": "#1c1510",
            "bg_mid": "#4a3728",
            "bg_bottom": "#120e0b",
            "accent": "#d4af37",
            "text": "#faf6ef",
            "subtext": "#e8dcc8",
            "band": "#2a2118",
        }
    if any(k in blob for k in ("bible", "faith", "scripture", "gospel", "church", "prayer")):
        return {
            "key": "faith",
            "bg_top": "#1e2a3a",
            "bg_mid": "#2c3e50",
            "bg_bottom": "#15202b",
            "accent": "#c9b896",
            "text": "#faf8f5",
            "subtext": "#ddd5c8",
            "band": "#243447",
        }
    if any(k in blob for k in ("christmas", "holiday", "halloween", "thanksgiving", "easter", "seasonal")):
        return {
            "key": "holiday",
            "bg_top": "#7f1d1d",
            "bg_mid": "#b45309",
            "bg_bottom": "#451a03",
            "accent": "#fde68a",
            "text": "#fffbeb",
            "subtext": "#fef3c7",
            "band": "#991b1b",
        }
    if any(k in blob for k in ("kid", "child", "children", "family", "elementary", "classroom")):
        return {
            "key": "kids",
            "bg_top": "#0369a1",
            "bg_mid": "#7c3aed",
            "bg_bottom": "#4338ca",
            "accent": "#fbbf24",
            "text": "#ffffff",
            "subtext": "#e0e7ff",
            "band": "#2563eb",
        }
    if any(k in blob for k in ("gold rush", "goldrush", "california", "history", "historic", "heritage")):
        return {
            "key": "history",
            "bg_top": "#292018",
            "bg_mid": "#6b4f2a",
            "bg_bottom": "#1a1208",
            "accent": "#e6c878",
            "text": "#fff8eb",
            "subtext": "#f0e2c8",
            "band": "#3d2e18",
        }
    if any(k in blob for k in ("brain", "puzzle", "word search", "crossword", "logic", "challenge")):
        return {
            "key": "puzzle",
            "bg_top": "#0f172a",
            "bg_mid": "#1e3a5f",
            "bg_bottom": "#0b1220",
            "accent": accent or "#38bdf8",
            "text": text or "#f8fafc",
            "subtext": "#cbd5e1",
            "band": "#1e293b",
        }
    return {
        "key": "professional",
        "bg_top": str(palette.get("primary") or "#1e3a5f"),
        "bg_mid": str(palette.get("secondary") or "#2563eb"),
        "bg_bottom": "#0f172a",
        "accent": accent or "#0ea5e9",
        "text": text or "#ffffff",
        "subtext": str(palette.get("muted") or "#cbd5e1"),
        "band": "#1e293b",
    }


def should_use_template_cover(cover: dict, package_id: str = "") -> bool:
    """Use premium template when there is no generated cover PNG."""
    from services.cover_agent import _has_cover_image

    pkg = package_id or str(cover.get("package_id") or "")
    if pkg and _has_cover_image(pkg):
        return False
    return True


def _title_px(title: str) -> str:
    size = _title_size_class(title)
    return {"cda-title-xs": "28px", "cda-title-sm": "34px", "cda-title-md": "38px"}.get(size, "44px")


def render_template_cover_preview_html(cover: dict) -> str:
    """Full-page portrait template cover for dashboard preview."""
    theme = resolve_cover_theme(cover)
    palette = cover.get("color_palette") if isinstance(cover.get("color_palette"), dict) else {}
    if palette.get("primary") and palette.get("secondary"):
        theme = {
            **theme,
            "bg_top": palette.get("primary", theme["bg_top"]),
            "bg_mid": palette.get("secondary", theme["bg_mid"]),
            "bg_bottom": palette.get("primary", theme["bg_bottom"]),
        }
    if palette.get("accent"):
        theme["accent"] = palette["accent"]
    if palette.get("text"):
        theme["text"] = palette["text"]
    if palette.get("muted"):
        theme["subtext"] = palette["muted"]
    title = str(cover.get("title") or "Untitled")
    subtitle = str(cover.get("subtitle") or "")
    author = str(cover.get("author") or "")
    font = _font_stack(cover.get("font_style") or "bold_display")
    title_size = cover_title_font_px(cover)
    sub_size = cover_subtitle_font_px(cover)
    size_class = _title_size_class(title)

    sub = f'<p class="cda-tpl-sub">{_e(subtitle)}</p>' if subtitle else ""
    auth = f'<p class="cda-tpl-author">{_e(author)}</p>' if author else ""
    pos = normalize_text_position(cover)
    body_style = text_layer_position_css(cover)

    return f"""<section class="sheet cover cda-template-cover cda-tpl-{theme["key"]}" data-cover-template="1">
<style>
.cda-template-cover {{
  position:relative; min-height:720px; width:100%; margin:0; padding:0; overflow:hidden;
  border:none; box-shadow:none; box-sizing:border-box;
  background: linear-gradient(165deg, {theme["bg_top"]} 0%, {theme["bg_mid"]} 42%, {theme["bg_bottom"]} 100%);
  font-family:{font};
}}
.cda-template-cover .cda-tpl-glow {{
  position:absolute; inset:0;
  background: radial-gradient(circle at 50% 28%, {theme["accent"]}33 0%, transparent 58%);
  pointer-events:none;
}}
.cda-template-cover .cda-tpl-orb {{
  position:absolute; border-radius:50%; opacity:0.14; background:{theme["accent"]};
}}
.cda-template-cover .cda-tpl-orb-a {{ width:220px; height:220px; top:-40px; right:-50px; }}
.cda-template-cover .cda-tpl-orb-b {{ width:160px; height:160px; bottom:80px; left:-40px; }}
.cda-template-cover .cda-tpl-band {{
  position:absolute; left:0; right:0; bottom:0; height:18%;
  background: linear-gradient(180deg, transparent 0%, {theme["band"]}cc 100%);
}}
.cda-template-cover .cda-tpl-body {{
  {body_style} font-family:{font};
}}
.cda-template-cover .cda-tpl-title {{
  margin:0; color:{theme["text"]}; font-weight:800; line-height:1.08;
  letter-spacing:-0.02em; max-width:92%; text-wrap:balance;
  font-size:{title_size};
}}
.cda-template-cover .cda-tpl-title.cda-title-xs {{ font-size:28px; }}
.cda-template-cover .cda-tpl-title.cda-title-sm {{ font-size:34px; }}
.cda-template-cover .cda-tpl-title.cda-title-md {{ font-size:38px; }}
.cda-template-cover .cda-tpl-sub {{
  margin:14px 0 0; color:{theme["subtext"]}; font-size:{sub_size}; line-height:1.35; max-width:88%;
}}
.cda-template-cover .cda-tpl-author {{
  margin:18px 0 0; color:{theme["subtext"]}; font-size:13px; letter-spacing:0.08em;
  text-transform:uppercase; opacity:0.92;
}}
</style>
<div class="cda-tpl-glow"></div>
<div class="cda-tpl-orb cda-tpl-orb-a"></div>
<div class="cda-tpl-orb cda-tpl-orb-b"></div>
<div class="cda-tpl-band"></div>
<div class="cda-tpl-body" data-editable-cover-text="1"
  data-text-x="{pos["x"]}" data-text-y="{pos["y"]}" data-text-align="{pos["align"]}">
  <h1 class="cda-tpl-title {size_class}">{_e(title)}</h1>
  {sub}
  {auth}
</div>
</section>"""


def render_template_cover_pdf_html(cover: dict) -> str:
    """Full-page template cover for ebook PDF export (xhtml2pdf-safe)."""
    theme = resolve_cover_theme(cover)
    title = str(cover.get("title") or "Untitled")
    subtitle = str(cover.get("subtitle") or "")
    author = str(cover.get("author") or "")
    sub = (
        f'<p style="margin:10pt 0 0;font-size:13pt;color:{theme["subtext"]};text-align:center;">{_e(subtitle)}</p>'
        if subtitle
        else ""
    )
    auth = (
        f'<p style="margin:14pt 0 0;font-size:9pt;color:{theme["subtext"]};text-align:center;'
        f'letter-spacing:0.08em;text-transform:uppercase;">{_e(author)}</p>'
        if author
        else ""
    )
    return f"""<section class="pdf-page cover-page cda-pdf-template-cover">
<table width="100%" height="100%" cellpadding="0" cellspacing="0"
  style="width:100%;height:9.25in;background-color:{theme["bg_mid"]};">
<tr><td align="center" valign="middle" style="padding:48pt 36pt 64pt;background-color:{theme["bg_mid"]};">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center" style="font-size:28pt;font-weight:bold;color:{theme["text"]};line-height:1.1;">
      {_e(title)}
    </td></tr>
    <tr><td align="center">{sub}{auth}</td></tr>
  </table>
</td></tr>
</table>
</section>"""


def draw_template_cover_pdf_page(pdf, cover: dict, layout) -> None:
    """ReportLab full-page template for Word Search PDF covers without PNG."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter

    theme = resolve_cover_theme(cover)
    page_w, page_h = letter
    title = str(cover.get("title") or "Untitled")
    subtitle = str(cover.get("subtitle") or "")
    author = str(cover.get("author") or "")

    pdf.setFillColor(colors.HexColor(theme["bg_bottom"]))
    pdf.rect(0, 0, page_w, page_h, fill=1, stroke=0)
    pdf.setFillColor(colors.HexColor(theme["bg_mid"]))
    pdf.rect(0, page_h * 0.18, page_w, page_h * 0.72, fill=1, stroke=0)
    pdf.setFillColor(colors.HexColor(theme["bg_top"]))
    pdf.rect(0, page_h * 0.55, page_w, page_h * 0.45, fill=1, stroke=0)

    pdf.setFillColor(colors.HexColor(theme["text"]))
    pdf.setFont("Helvetica-Bold", 30 if len(title) < 28 else 24)
    pdf.drawCentredString(page_w / 2, page_h * 0.30, title[:80])

    if subtitle:
        pdf.setFillColor(colors.HexColor(theme["subtext"]))
        pdf.setFont("Helvetica", 14)
        pdf.drawCentredString(page_w / 2, page_h * 0.24, subtitle[:120])

    if author:
        pdf.setFont("Helvetica", 11)
        pdf.drawCentredString(page_w / 2, page_h * 0.16, author[:80])

    layout.cover_page_count = 1
    layout.page_count += 1
    layout.outer_box_count += 1
