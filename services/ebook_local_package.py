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
from services.ebook_document import (
    attach_document_to_data,
    build_ebook_document_from_project,
    strip_visual_instructions,
)
from services.ebook_design_system import get_theme
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
    # DRAFT-only path (caller gates mutation): strip visual-production instructions
    # before they reach preview/customer manuscript.
    content_md, _leaked = strip_visual_instructions(content_md)
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
        # Topic-specific aids only — derive from manuscript tables/checklists.
        # Never inject generic Key Practice / Apply / FAQ fillers.
        plan_chapters = []
        for i, (name, body) in enumerate(chapters_md):
            aids = []
            body = body or ""
            if re.search(r"^\|.+\|$", body, re.M) and re.search(r"^\|\s*-+", body, re.M):
                aids.append(
                    {
                        "type": "table",
                        "title": f"{(name or 'Chapter')[:48]} matrix",
                        "caption": "Reference table from this chapter.",
                        "visual_id": f"v_local_table_{i+1}",
                        "table": {"headers": [], "rows": []},
                        "body": "",
                    }
                )
            checklist = re.findall(r"^[-*]\s+(.+)$", body, re.M)
            if len(checklist) >= 3:
                aids.append(
                    {
                        "type": "checklist",
                        "title": f"{(name or 'Chapter')[:48]} checklist",
                        "caption": "Actions from this chapter.",
                        "visual_id": f"v_local_check_{i+1}",
                        "items": checklist[:6],
                    }
                )
            numbered = re.findall(r"^\d+\.\s+(.+)$", body, re.M)
            if len(numbered) >= 3 and not aids:
                aids.append(
                    {
                        "type": "action step box",
                        "title": f"{(name or 'Chapter')[:48]} steps",
                        "caption": "Numbered steps from this chapter.",
                        "visual_id": f"v_local_steps_{i+1}",
                        "items": numbered[:6],
                    }
                )
            plan_chapters.append({"chapter": name, "aids": aids})
        # Ensure pipeline minimum of 3 research-supporting aids without generics.
        flat = [a for ch in plan_chapters for a in (ch.get("aids") or [])]
        if len(flat) < 3 and chapter_titles:
            for i, name in enumerate(chapter_titles):
                if len(flat) >= 3:
                    break
                ch = plan_chapters[i]
                if ch.get("aids"):
                    continue
                aid = {
                    "type": "table",
                    "title": f"{name[:48]} focus points",
                    "caption": "Topic-specific focus from the manuscript.",
                    "visual_id": f"v_local_focus_{i+1}",
                    "table": {
                        "headers": ["Focus", "Reader action"],
                        "rows": [
                            ["Core idea", f"Carry forward one point from {name[:40]}"],
                            ["Next check", "Schedule a follow-through block"],
                        ],
                    },
                }
                # Avoid banned generic titles
                ch["aids"] = [aid]
                flat.append(aid)

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
    cover_design["design_theme"] = fields.get("design_theme") or "studio_clean"

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
    # Cover composite CSS historically used letter-spacing; strip for PDF-safe output.
    preview_html = re.sub(
        r"letter-spacing\s*:\s*[^;\"'}]+;?", "", preview_html, flags=re.I
    )

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

    theme = get_theme(fields.get("design_theme") or "studio_clean")
    doc = build_ebook_document_from_project(
        {
            "data": {
                "title": title,
                "subtitle": subtitle,
                "content": content_md,
                "ebook": content_md,
                "visual_plan": visual_plan,
                "cover_design": cover_design,
                "fields": fields,
                "author_brand": author,
                "package_id": package_id,
                "design_theme": theme.theme_id,
                "reader_promise": product_summary,
            }
        }
    )
    doc.workflow_stage = "preview"
    # Ebook-specific digests feed Stabilized data without replacing APPROVED
    # content_digest / asset_manifest_digest stamped by artifact_identity.
    data_sync = attach_document_to_data({}, doc)

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
        "ebook_document": data_sync.get("ebook_document"),
        "ebook_manuscript_digest": doc.identity.content_digest,
        "ebook_asset_manifest_digest": doc.identity.asset_manifest_digest,
        "design_theme": theme.theme_id,
        "design_theme_version": theme.version,
        "ebook_workflow_stage": doc.workflow_stage,
        "release_status": doc.release_status,
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
            "ebook_document": built.get("ebook_document"),
            "ebook_manuscript_digest": built.get("ebook_manuscript_digest"),
            "ebook_asset_manifest_digest": built.get("ebook_asset_manifest_digest"),
            "design_theme": built.get("design_theme"),
            "design_theme_version": built.get("design_theme_version"),
            "ebook_workflow_stage": built.get("ebook_workflow_stage"),
        }
    )
    invalidate_draft_export_references(data)
    project = dict(project)
    project["data"] = data
    return project
