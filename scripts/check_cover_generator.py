#!/usr/bin/env python3
"""Smoke test for the shared cover generator (local API + services)."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

BASE = os.environ.get("COVER_CHECK_BASE", "http://127.0.0.1:5000")


def api_post(path: str, body: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            data = {"error": payload}
        return exc.code, data


def check(name: str, ok: bool, detail: str = "") -> bool:
    mark = "PASS" if ok else "FAIL"
    line = f"[{mark}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


def main() -> int:
    import database
    from services.cover_agent import COVER_VERSION, _cover_image_path, _has_cover_image
    from services.product_cover_agent import preview_cover, validate_cover_project

    print(f"Cover generator health check ({BASE})\n")

    ok = True
    projects = database.list_projects()
    ok &= check("Database reachable", bool(projects), f"{len(projects)} project(s)")

    ws = next(
        (
            p
            for p in projects
            if (p.get("data") or {}).get("product_type") == "word_search"
            and (p.get("data") or {}).get("cover_design")
        ),
        None,
    )
    if not ws:
        ws = projects[0] if projects else None

    if not ws:
        print("No projects found — skipping live project checks.")
        return 1

    pid = ws["id"]
    data = ws.get("data") or {}
    cover = data.get("cover_design") or {}
    package_id = str(data.get("package_id") or cover.get("package_id") or "")
    title = cover.get("title") or data.get("title") or ws.get("name") or "Untitled"

    ok &= check("Sample project loaded", True, f"id={pid}, title={title!r}")
    ok &= check("package_id present", bool(package_id), package_id or "missing")

    try:
        validate_cover_project(ws)
        ok &= check("validate_cover_project", True)
    except ValueError as exc:
        ok &= check("validate_cover_project", False, str(exc))

    try:
        preview = preview_cover(ws, {"title": title})
        html = preview.get("preview_html") or ""
        ok &= check("preview_cover (service)", bool(html), f"{len(html)} chars")
        ok &= check("cover version current", int(preview.get("version") or 0) >= COVER_VERSION, f"v{preview.get('version')}")
        ok &= check("no accent bar in preview", "cda-tpl-accent" not in html and "cda-comp-accent" not in html)
        ok &= check("text overlay when AI image", "data-cover-text-overlay" in html or not preview.get("use_ai_image"))
    except Exception as exc:
        ok &= check("preview_cover (service)", False, str(exc))

    if package_id:
        has_img = _has_cover_image(package_id)
        img_path = _cover_image_path(package_id)
        ok &= check("cover PNG on disk", has_img, img_path or "not found")

    status, body = api_post("/cover-design/preview", {"project_id": pid, "cover": {"title": title}})
    ok &= check("POST /cover-design/preview", status == 200, f"HTTP {status}")
    if status == 200:
        cd = body.get("cover_design") or {}
        ok &= check("API preview_html", bool(body.get("preview_html") or cd.get("preview_html")))

    status, body = api_post("/cover-design/regenerate-image", {"project_id": pid})
    regen_ok = status == 200 and body.get("image_ok")
    ok &= check("POST /cover-design/regenerate-image", regen_ok, f"HTTP {status}, image_ok={body.get('image_ok')}")
    if status != 200:
        err = body.get("error") or body
        print(f"       regenerate detail: {err}")

    print()
    if ok:
        print("Overall: cover generator is working.")
        return 0
    print("Overall: one or more checks failed — see details above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
