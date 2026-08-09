"""Polished visual fallbacks when generated images are missing -- never show raw prompts."""
from __future__ import annotations

import base64
import html
import os
import re
from typing import Any

EXPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "exports")

_PROMPT_PREFIXES = (
    "create a", "design a", "generate a", "make a", "illustrate", "show a realistic",
    "show a", "draw a", "render a",
)


def _e(value: Any) -> str:
    return html.escape(str(value or ""))


def _norm_title(title: str) -> str:
    return re.sub(r"\s+", " ", str(title or "").strip().lower())


def looks_like_prompt(text: str) -> bool:
    t = str(text or "").strip().lower()
    if len(t) > 120:
        return True
    return any(t.startswith(p) for p in _PROMPT_PREFIXES)


def safe_caption(caption: str) -> str:
    cap = str(caption or "").strip()
    return "" if looks_like_prompt(cap) else cap


def image_asset_path(package_id: str, visual_id: str) -> str | None:
    if not package_id or not visual_id:
        return None
    path = os.path.join(EXPORTS_DIR, package_id, f"img_{visual_id}.png")
    return path if os.path.isfile(path) else None


def pdf_image_data_uri(package_id: str, visual_id: str) -> str:
    path = image_asset_path(package_id, visual_id)
    if not path:
        return ""
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
        if not raw:
            return ""
        return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
    except OSError:
        return ""


def package_id_from_url(url: str) -> str:
    match = re.search(r"/download/([a-f0-9]{32})/img_", str(url or ""))
    return match.group(1) if match else ""


def _infographic_body(title: str, *, pdf: bool) -> str:
    t = _norm_title(title)
    if "title formula" in t:
        if pdf:
            return (
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
        return (
            '<div class="va-fb-formula">'
            '<div class="va-fb-formula-row">'
            '<span class="va-fb-part">Main Keyword</span><span class="va-fb-sep">+</span>'
            '<span class="va-fb-part">Style Descriptor</span><span class="va-fb-sep">+</span>'
            '<span class="va-fb-part">Buyer Benefit</span>'
            "</div>"
            '<div class="va-fb-note">Strong Etsy title structure</div>'
            "</div>"
        )
    if "one view" in t or "optimization in one" in t:
        if pdf:
            return (
                '<table class="pdf-principles" width="100%" cellpadding="0" cellspacing="6">'
                "<tr>"
                '<td><b>Find</b><br/>Keywords &amp; tags</td>'
                '<td><b>Convert</b><br/>Photos &amp; copy</td>'
                '<td><b>Improve</b><br/>Measure &amp; refine</td>'
                "</tr></table>"
            )
        return (
            '<div class="va-fb-principles">'
            '<div class="va-fb-principle"><b>Find</b><span>Keywords &amp; tags</span></div>'
            '<div class="va-fb-principle"><b>Convert</b><span>Photos &amp; copy</span></div>'
            '<div class="va-fb-principle"><b>Improve</b><span>Measure &amp; refine</span></div>'
            "</div>"
        )
    if "high-trust" in t or "listing visual" in t:
        if pdf:
            return (
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
                '<div class="pdf-listing-ship">✓ Free shipping · ✓ Ready to ship · ✓ Ready to ship in 1-3 days</div>'
                '<div class="pdf-listing-trust">★ Top Rated Seller</div>'
                "</div>"
            )
        return (
            '<div class="va-fb-listing">'
            '<div class="va-fb-listing-row">'
            '<div class="va-fb-listing-thumb"></div>'
            '<div class="va-fb-listing-body">'
            '<div class="va-fb-listing-title">Handmade Personalized Bookmark -- Custom Name Gift</div>'
            '<div class="va-fb-listing-stars">★★★★★ <span>(128 reviews)</span></div>'
            '<div class="va-fb-listing-meta">In 12 carts · 48 sold this week</div>'
            '<div class="va-fb-listing-price">$24.00</div>'
            "</div></div>"
            '<div class="va-fb-listing-trust">★ Top Rated Seller · ✓ Free shipping</div>'
            "</div>"
        )
    if "ai model categor" in t or "model type" in t or "types of ai" in t:
        cats = [
            ("Language Models", "Best for text, Q&amp;A, summarization, drafting, and code help."),
            ("Image Models", "Best for visuals, product mockups, ads, and creative concepts."),
            ("Code Models", "Best for debugging, code generation, and technical workflows."),
            ("Multimodal Models", "Best when the task uses text, images, audio, or documents together."),
            ("Embedding Models", "Best for search, recommendations, and RAG retrieval."),
        ]
        if pdf:
            rows = "".join(
                f'<tr><td style="font-weight:bold;color:#312e81;padding:6pt 8pt;">{_e(name)}</td>'
                f'<td style="padding:6pt 8pt;">{_e(desc)}</td></tr>'
                for name, desc in cats
            )
            return (
                '<table class="pdf-table" width="100%" cellpadding="0" cellspacing="0" '
                'style="border-collapse:collapse;margin:8pt 0;">'
                f"{rows}</table>"
            )
        return (
            '<div class="va-fb-categories">'
            + "".join(
                f'<div class="va-fb-cat-row">'
                f'<span class="va-fb-cat-name">{_e(name)}</span>'
                f'<span class="va-fb-cat-desc">{_e(desc)}</span>'
                f"</div>"
                for name, desc in cats
            )
            + "</div>"
        )
    if "final tip" in t:
        questions = [
            "What task must this model perform?",
            "What data will the model receive?",
            "What quality score is acceptable?",
            "What is the maximum cost per run?",
            "What privacy or risk rule must be checked before launch?",
        ]
        if pdf:
            items = "".join(
                f'<tr><td style="padding:6pt 8pt;vertical-align:top;">'
                f'<b style="color:#312e81;">{i}.</b></td>'
                f'<td style="padding:6pt 8pt;">{_e(q)}</td></tr>'
                for i, q in enumerate(questions, 1)
            )
            return (
                '<table class="pdf-table" width="100%" cellpadding="0" cellspacing="0" '
                'style="border-collapse:collapse;margin:8pt 0;">'
                f"{items}</table>"
            )
        return (
            '<div class="va-fb-tips">'
            + "".join(
                f'<div class="va-fb-tip-row"><b class="va-fb-tip-num">{i}.</b>'
                f'<span class="va-fb-tip-q">{_e(q)}</span></div>'
                for i, q in enumerate(questions, 1)
            )
            + "</div>"
        )
    if "roadmap" in t or "ebook roadmap" in t:
        if pdf:
            return (
                '<table class="pdf-principles" width="100%" cellpadding="4" cellspacing="4">'
                "<tr>"
                '<td><b>1</b><br/>Strategy</td>'
                '<td><b>2</b><br/>Titles</td>'
                '<td><b>3</b><br/>Convert</td>'
                "</tr></table>"
            )
        return (
            '<div class="va-fb-principles va-fb-roadmap">'
            '<div class="va-fb-principle"><b>1</b><span>Strategy</span></div>'
            '<div class="va-fb-principle"><b>2</b><span>Titles</span></div>'
            '<div class="va-fb-principle"><b>3</b><span>Convert</span></div>'
            "</div>"
        )
    label = _e(title or "Visual summary")
    if pdf:
        return f'<div class="pdf-info-card"><div class="pdf-formula-note">{label}</div></div>'
    return f'<div class="va-fb-generic"><div class="va-fb-generic-title">{label}</div></div>'


def _stock_photo_body(title: str, *, pdf: bool) -> str:
    t = _norm_title(title)
    if pdf:
        return (
            '<table width="100%" cellpadding="0" cellspacing="0" '
            'style="background:#f8fafc;border:1pt solid #e2e8f0;border-radius:8pt;">'
            "<tr><td style=\"padding:10pt;text-align:center;\">"
            '<div style="background:#ddd6fe;height:48pt;border-radius:6pt;margin-bottom:8pt;"></div>'
            '<div style="font-size:8pt;color:#64748b;">Product listing preview</div>'
            "</td></tr></table>"
        )
    if any(k in t for k in ("etsy", "listing", "marketplace", "ecommerce", "trust")):
        return (
            '<div class="va-fb-ecommerce">'
            '<div class="va-fb-device va-fb-laptop"><div class="va-fb-screen">'
            '<div class="va-fb-search">Search Etsy listings...</div>'
            '<div class="va-fb-mini-cards">'
            '<div class="va-fb-mini"><div class="va-fb-mini-img"></div><span>Top Seller</span></div>'
            '<div class="va-fb-mini"><div class="va-fb-mini-img"></div><span>Trending</span></div>'
            "</div></div></div>"
            '<div class="va-fb-device va-fb-phone"><div class="va-fb-screen va-fb-phone-screen">'
            '<div class="va-fb-phone-card"></div></div></div>'
            "</div>"
        )
    return (
        '<div class="va-fb-photo">'
        '<div class="va-fb-photo-gradient"></div>'
        '<div class="va-fb-photo-label">Professional visual</div>'
        "</div>"
    )


def preview_image_fallback_html(aid: dict) -> str:
    """Preview fallback card -- title only inside card; caption stays on the visual aid."""
    title = str(aid.get("title") or "Visual").strip()
    atype = str(aid.get("type") or "infographic").lower()
    if atype == "stock photo":
        body = _stock_photo_body(title, pdf=False)
    else:
        body = _infographic_body(title, pdf=False)
    return f'<div class="va-img-fallback va-fb-card">{body}</div>'


def pdf_image_fallback_html(aid: dict) -> str:
    title = str(aid.get("title") or "Visual").strip()
    atype = str(aid.get("type") or "infographic").lower()
    if atype == "stock photo":
        return _stock_photo_body(title, pdf=True)
    return _infographic_body(title, pdf=True)


def mermaid_static_flow_html(code: str, title: str = "Diagram") -> str:
    """Static boxed flow -- no raw Mermaid source shown to readers."""
    nodes = re.findall(r"\[([^\]]+)\]", str(code or ""))
    nodes = [n.strip() for n in nodes if n.strip()][:6]
    if not nodes:
        return _infographic_body(title, pdf=False)
    parts = []
    for i, node in enumerate(nodes):
        parts.append(f'<div class="va-flow-step"><span class="va-flow-num">{i + 1}</span>{_e(node)}</div>')
        if i < len(nodes) - 1:
            parts.append('<div class="va-flow-arrow">↓</div>')
    return f'<div class="va-flow-static">{"".join(parts)}</div>'


def preview_chart_static_html(chart_data: dict, title: str = "") -> str:
    labels = chart_data.get("labels") or []
    values = [float(v) for v in (chart_data.get("values") or [])]
    if not labels or not values:
        return ""
    n = min(len(labels), len(values))
    labels, values = labels[:n], values[:n]
    max_val = max(values) or 1.0
    colors = ["#7c3aed", "#0d9488", "#d97706", "#2563eb", "#db2777"]
    bars = []
    for i, (lbl, val) in enumerate(zip(labels, values)):
        h = max(18, int(72 * val / max_val))
        color = colors[i % len(colors)]
        bars.append(
            f'<div class="va-bar-col">'
            f'<div class="va-bar-val">{_e(str(int(val) if float(val).is_integer() else round(val, 1)))}</div>'
            f'<div class="va-bar-fill" style="height:{h}px;background:{color};"></div>'
            f'<div class="va-bar-lbl">{_e(str(lbl)[:18])}</div>'
            "</div>"
        )
    heading = f'<div class="va-chart-static-title">{_e(title)}</div>' if title else ""
    return f'<div class="va-chart-static">{heading}<div class="va-bar-row">{"".join(bars)}</div></div>'
