"""Local ebook packaging path — zero paid API calls.

Used when export needs a visual package but /enhance-ebook was never run,
or when tests regenerate Screens with Purpose-class books from stored markdown.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any

from services.ebook_cover_local import cover_design_from_local, proposed_cover_prompt
from services.ebook_interior_visuals import (
    is_screens_parenting_topic,
    rewrite_mechanical_headings,
    screens_visual_plan,
)
from services.cover_agent import apply_cover_to_preview
from services.ebook_package import (
    EXPORTS_DIR,
    _split_chapters,
    _write_package,
    render_aid_html,
    render_preview_html,
    render_txt,
)


def _subtitle_from_content(title: str, content_md: str, fields: dict) -> str:
    sub = (fields.get("subtitle") or "").strip()
    if sub:
        return sub
    # Prefer subtitle after colon in H1
    m = re.search(r"^#\s+[^:\n]+:\s*(.+)$", content_md, re.M)
    if m:
        return m.group(1).strip()[:180]
    if "screen" in (title + content_md[:400]).lower():
        return (
            "A Practical Guide to Low-Conflict, Developmentally Appropriate "
            "Screen Habits for Young Children"
        )
    return "A practical guide"


def build_local_ebook_package(
    title: str,
    content_md: str,
    fields: dict | None = None,
    *,
    package_id: str = "",
) -> dict[str, Any]:
    """Build visual_plan + preview + local cover without OpenAI/Tavily/images APIs."""
    fields = dict(fields or {})
    package_id = (package_id or "").strip() or uuid.uuid4().hex
    topic = (fields.get("topic") or title or "").strip()
    audience = (fields.get("audience") or "").strip()
    author = (
        fields.get("author_brand")
        or fields.get("author")
        or "Digital Product Factory"
    ).strip()

    content_md = rewrite_mechanical_headings(content_md, title=title, topic=topic)
    _intro, chapters_md = _split_chapters(content_md)
    chapter_titles = [c[0] for c in chapters_md if c and c[0]]

    if is_screens_parenting_topic(title, topic, content_md):
        plan_chapters = screens_visual_plan(chapter_titles)
        if not audience:
            audience = (
                "Parents and caregivers of toddlers, preschoolers, "
                "and early-elementary children"
            )
            fields["audience"] = audience
    else:
        plan_chapters = []
        for i, name in enumerate(chapter_titles):
            aid = {
                "type": "tip",
                "title": f"Key practice — {name[:48]}",
                "caption": "Apply one idea from this chapter today.",
                "visual_id": f"v_local_{i+1}",
                "body": (
                    f"<table class='va-table'><tr><td><b>Try this:</b> "
                    f"Choose one action from <em>{_escape(name)}</em> and schedule "
                    f"it in the next 24 hours.</td></tr></table>"
                ),
            }
            plan_chapters.append({"chapter": name, "aids": [aid]})

    # Ensure aids have renderable html via render_aid_html when type supported
    for ch in plan_chapters:
        for aid in ch.get("aids") or []:
            if not aid.get("rendered_html"):
                try:
                    aid["rendered_html"] = render_aid_html(aid, package_id)
                except Exception:
                    aid["rendered_html"] = aid.get("body") or aid.get("html") or ""

    subtitle = _subtitle_from_content(title, content_md, fields)
    fields["subtitle"] = subtitle
    product_summary = (
        fields.get("product_summary")
        or (
            f"{title} helps {audience or 'readers'} build practical, low-conflict "
            f"habits around {topic or 'the topic'}."
        )
    )
    cover_prompt = proposed_cover_prompt(
        title=title, subtitle=subtitle, audience=audience, topic=topic
    )

    cover_design = cover_design_from_local(
        title=title,
        subtitle=subtitle,
        author=author,
        package_id=package_id,
        topic=topic,
        audience=audience,
        fields=fields,
    )

    preview_html = render_preview_html(
        title,
        subtitle,
        content_md,
        plan_chapters,
        package_id,
        product_summary,
        cover_design,
        topic=topic,
    )
    preview_html = apply_cover_to_preview(preview_html, cover_design)

    txt_doc = render_txt(title, subtitle, content_md, plan_chapters)
    visual_plan = {"chapters": plan_chapters}
    visual_json = json.dumps(
        {
            "title": title,
            "subtitle": subtitle,
            "cover_prompt": cover_prompt,
            "product_summary": product_summary,
            "chapters": plan_chapters,
            "local_only": True,
        },
        indent=2,
    )

    _write_package(
        package_id,
        {
            "ebook.html": preview_html,
            "ebook.txt": txt_doc,
            "visual_plan.json": visual_json,
            "cover_prompt.txt": cover_prompt,
            "product_summary.txt": product_summary,
        },
    )

    return {
        "package_id": package_id,
        "title": title,
        "subtitle": subtitle,
        "content": content_md,
        "preview_html": preview_html,
        "visual_plan": visual_plan,
        "cover_design": cover_design,
        "cover_prompt": cover_prompt,
        "product_summary": product_summary,
        "fields": fields,
        "image_jobs": [],  # never auto-queue paid images
        "local_only": True,
        "exports_dir": os.path.join(EXPORTS_DIR, package_id),
    }


def _escape(s: str) -> str:
    import html as _html

    return _html.escape(s or "")


def ensure_ebook_visual_package(project: dict) -> dict:
    """If an ebook project lacks visual_plan/preview, build a local package in place.

    Content mutation is gated by ``assert_content_mutation_allowed``:
    DRAFT may assemble missing visuals; APPROVED requires Create Draft Revision;
    LOCKED is blocked. Successful DRAFT mutation clears stale export refs.
    """
    data = dict(project.get("data") or {})
    product_type = (data.get("product_type") or project.get("type") or "").lower()
    if product_type not in {"ebook", ""} and project.get("type") != "ebook":
        # Only auto-build for ebook projects
        if data.get("product_type") != "ebook" and project.get("type") != "ebook":
            return project

    content = (data.get("content") or data.get("ebook") or "").strip()
    if not content:
        return project
    if data.get("visual_plan") and data.get("preview_html") and data.get("cover_design"):
        return project

    from services.quality.artifact_state import (
        assert_content_mutation_allowed,
        invalidate_draft_export_references,
    )

    # Shared write policy — no APPROVED/LOCKED content/cover/asset mutation.
    assert_content_mutation_allowed(data, action="build ebook visual package")

    title = (data.get("title") or project.get("name") or "Untitled Product").strip()
    fields = dict(data.get("fields") or {})
    if not fields.get("topic"):
        fields["topic"] = data.get("source") or title
    if data.get("subtitle"):
        fields["subtitle"] = data["subtitle"]

    pkg = str(data.get("package_id") or data.get("export_package_id") or "").strip()
    built = build_local_ebook_package(title, content, fields, package_id=pkg)
    data.update(
        {
            "title": built["title"],
            "subtitle": built["subtitle"],
            "content": built["content"],
            "ebook": built["content"],
            "preview_html": built["preview_html"],
            "visual_plan": built["visual_plan"],
            "cover_design": built["cover_design"],
            "cover_prompt": built["cover_prompt"],
            "product_summary": built["product_summary"],
            "package_id": built["package_id"],
            "fields": built["fields"],
            "product_type": "ebook",
            "local_visual_package": True,
        }
    )
    invalidate_draft_export_references(data)
    project = dict(project)
    project["data"] = data
    return project
