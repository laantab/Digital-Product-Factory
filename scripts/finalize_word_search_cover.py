#!/usr/bin/env python3
"""Finalize a Word Search cover for production (single pass)."""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import database
from services.product_cover_agent import finalize_word_search_production_cover


def main() -> int:
    project_id = int(sys.argv[1]) if len(sys.argv) > 1 else 73
    project = database.get_project(project_id)
    if not project:
        print(f"Project {project_id} not found.")
        return 1

    result = finalize_word_search_production_cover(project)
    data = result["data"]
    cover = result["cover_design"]
    qa = result["quality"]

    database.update_project(project_id, None, data, None)

    print(json.dumps({
        "project_id": project_id,
        "title": cover.get("title"),
        "subtitle": cover.get("subtitle"),
        "author": cover.get("author"),
        "cover_version": cover.get("version"),
        "cover_finalized": cover.get("cover_finalized"),
        "quality_passed": qa.get("passed"),
        "quality_score": qa.get("score"),
        "regenerated_image": result.get("regenerated_image"),
        "asset_url": result.get("asset_url"),
        "package_id": data.get("package_id"),
        "preview_html_length": len(result.get("preview_html") or ""),
        "has_pdf_bytes": bool(result.get("pdf_bytes")),
    }, indent=2))
    return 0 if qa.get("passed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
