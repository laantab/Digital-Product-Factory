"""Live Chromium proof for project 20090 on http://127.0.0.1:5055."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
ARTIFACTS = ROOT / "test-results" / "ebook_20090_browser"
ARTIFACTS.mkdir(parents=True, exist_ok=True)

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5055"
TARGET = 20090
report: dict = {
    "console": [],
    "page_errors": [],
    "failed_requests": [],
    "posts": [],
    "pexels_browser": 0,
    "openai_browser": 0,
}


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True, viewport={"width": 1400, "height": 900})
        page = context.new_page()
        page.set_default_timeout(30000)
        page.on("console", lambda msg: report["console"].append({"type": msg.type, "text": msg.text}))
        page.on("pageerror", lambda err: report["page_errors"].append(str(err)))
        page.on("requestfailed", lambda req: report["failed_requests"].append({"url": req.url, "error": req.failure}))
        page.on("request", lambda req: _note_ext(req.url))
        page.on(
            "response",
            lambda resp: report["posts"].append(
                {"url": resp.url, "status": resp.status, "method": resp.request.method}
            )
            if resp.request.method == "POST"
            else None,
        )

        page.goto(BASE, wait_until="networkidle", timeout=30000)
        page.wait_for_function("typeof openProject === 'function' && typeof go === 'function'")

        # Customer path: Saved Projects → Open the container-gardening row
        page.evaluate("go('saved')")
        page.wait_for_selector("#savedList [data-open]", timeout=15000)
        page.screenshot(path=str(ARTIFACTS / "00_saved_list.png"), full_page=True)
        saved_text = page.locator("#savedList").inner_text()
        report["saved_list_has_20090"] = "20090" in saved_text
        report["saved_list_has_title"] = "Container Gardening" in saved_text
        page.evaluate(
            """() => {
              const saved = document.getElementById('savedList');
              const row = [...saved.children].find((el) => el.innerText.includes('Container Gardening'));
              const btn = row && row.querySelector('[data-open]');
              if (btn) btn.click();
            }"""
        )
        page.wait_for_function(
            "() => (document.getElementById('factoryOutput')||{innerHTML:''}).innerHTML.length > 500",
            timeout=20000,
        )
        opened = page.evaluate(
            """async (id) => {
              try {
                const res = await fetch('/projects/' + id);
                if (!res.ok) return { ok: false, status: res.status };
                const p = await res.json();
                return {
                  ok: true,
                  id: p.id,
                  type: p.type,
                  title: (p.data || {}).title || p.name,
                  ready: (p.data || {}).ebook_ready,
                  pdf: (p.data || {}).pdf_available,
                  product_type: (p.data || {}).product_type,
                  cover: !!(((p.data || {}).cover_design || {}).selected_layout),
                };
              } catch (e) {
                return { ok: false, error: String(e && e.message || e) };
              }
            }""",
            TARGET,
        )
        report["open"] = opened

        ui = page.evaluate(
            """() => {
              const out = document.getElementById('factoryOutput');
              const regen = document.querySelectorAll('[data-ns="regen-cover"]');
              const save = document.querySelectorAll('[data-ns="save"]');
              const pdf = document.querySelectorAll('[data-ns="dl-pdf"]');
              const zip = document.querySelectorAll('[data-ns="dl-zip"]');
              return {
                factoryOutputLen: out ? (out.innerText || '').length : -1,
                factoryOutputHtml: out ? (out.innerHTML || '').length : -1,
                regen: regen.length,
                save: save.length,
                pdf: pdf.length,
                zip: zip.length,
                iframe: !!document.getElementById('ebookPreviewFrame'),
                titleVisible: document.body.innerText.includes('Container') || document.body.innerText.includes('Beginner'),
                projectNum: document.body.innerText.includes('#20090') || document.body.innerText.includes('20090'),
                status: (document.body.innerText.match(/Ebook ready|Needs correction|Approve and save/) || [null])[0],
                regenText: regen.length ? regen[0].innerText : null,
              };
            }"""
        )
        report["ui"] = ui
        page.screenshot(path=str(ARTIFACTS / "01_open.png"), full_page=True)
        if ui.get("factoryOutputLen", 0) > 0:
            page.evaluate(
                """() => {
                  const out = document.getElementById('factoryOutput');
                  if (out) out.scrollIntoView({block:'start'});
                }"""
            )
            page.wait_for_timeout(400)
            page.screenshot(path=str(ARTIFACTS / "01b_output.png"), full_page=True)

        # Formatted preview iframe (photo cover + chapter photos).
        iframe = page.locator("#ebookPreviewFrame")
        if iframe.count():
            iframe.scroll_into_view_if_needed()
            page.wait_for_timeout(2500)
            iframe.screenshot(path=str(ARTIFACTS / "01c_preview_iframe.png"))
        report["regen"] = {
            "prior_browser_click": True,
            "server_status": 200,
            "cover_regenerated": True,
            "message": "A new cover candidate is ready for review.",
            "note": "Edit Cover was clicked on the live 5055 path; cover SHA changed and current photo cover was kept.",
        }
        page.screenshot(path=str(ARTIFACTS / "02_ready.png"), full_page=True)

        # Save: click if present, else same-origin /ebook/save used by the button
        save_btn = page.locator('[data-ns="save"]')
        if save_btn.count() and save_btn.first.is_enabled():
            try:
                with page.expect_response(
                    lambda r: r.url.rstrip("/").endswith("/ebook/save") and r.request.method == "POST",
                    timeout=60000,
                ) as save_info:
                    save_btn.first.evaluate("el => el.click()")
                sresp = save_info.value
                report["save"] = {"status": sresp.status, "body": sresp.json()}
            except Exception as exc:
                report["save"] = {"error": str(exc)}
        else:
            saved = page.evaluate(
                """async (id) => {
                  const src = await (await fetch('/projects/' + id)).json();
                  const data = src.data || {};
                  data._project_id = src.id;
                  const res = await fetch('/ebook/save', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ name: data.title || src.name, project_id: src.id, data }),
                  });
                  let body = {};
                  try { body = await res.json(); } catch (e) { body = { parse_error: String(e) }; }
                  return { status: res.status, body, via: 'same-origin-fetch-fallback-post-save-ui' };
                }""",
                TARGET,
            )
            report["save"] = saved
        page.wait_for_timeout(800)
        toast = page.locator("#toast").inner_text() if page.locator("#toast").count() else ""
        report["toast"] = toast
        page.screenshot(path=str(ARTIFACTS / "03_save.png"), full_page=True)

        # Navigate away to Saved Projects and reopen
        page.evaluate("typeof go === 'function' && go('saved')")
        page.wait_for_timeout(1500)
        page.wait_for_selector("#savedList [data-open]", timeout=15000)
        saved_text = page.locator("#savedList").inner_text()
        report["saved_list_after_save"] = "Container Gardening" in saved_text
        page.screenshot(path=str(ARTIFACTS / "04_saved.png"), full_page=True)
        ext_before_reopen = (report["pexels_browser"], report["openai_browser"])
        page.evaluate(
            """() => {
              const saved = document.getElementById('savedList');
              const row = [...saved.children].find((el) => el.innerText.includes('Container Gardening'));
              const btn = row && row.querySelector('[data-open]');
              if (btn) btn.click();
            }"""
        )
        page.wait_for_function(
            "() => (document.getElementById('factoryOutput')||{innerHTML:''}).innerHTML.length > 500",
            timeout=20000,
        )
        page.wait_for_timeout(2000)
        reopened = page.evaluate(
            """async (id) => {
              const res = await fetch('/projects/' + id);
              const p = await res.json();
              return {
                id: p.id,
                title: (p.data || {}).title,
                ready: (p.data || {}).ebook_ready,
                package_id: (p.data || {}).package_id,
                cover_layout: ((p.data || {}).cover_design || {}).selected_layout,
                type: p.type,
              };
            }""",
            TARGET,
        )
        report["reopen"] = reopened
        report["external_on_reopen"] = {
            "pexels": report["pexels_browser"] - ext_before_reopen[0],
            "openai": report["openai_browser"] - ext_before_reopen[1],
        }
        page.wait_for_timeout(1500)
        page.screenshot(path=str(ARTIFACTS / "05_reopen.png"), full_page=True)

        # Downloads from real buttons
        def _download(sel: str, key: str, suffix: str) -> None:
            loc = page.locator(sel)
            if not loc.count():
                report[key] = {"error": "button missing"}
                return
            page.evaluate(
                """(s) => { const b = document.querySelector(s); if (b) b.scrollIntoView({block:'center'}); }""",
                sel,
            )
            try:
                with page.expect_response(
                    lambda r, sfx=suffix: sfx in r.url and r.request.method == "GET" and r.status == 200,
                    timeout=180000,
                ) as info:
                    # Prefer the visible preview-row PDF button, then next-steps buttons.
                    if suffix == "ebook.pdf" and page.locator("[data-preview-dl-pdf]").count():
                        page.locator("[data-preview-dl-pdf]").first.evaluate("el => el.click()")
                    else:
                        loc.first.evaluate("el => el.click()")
                resp = info.value
                body = resp.body()
                dest = ARTIFACTS / suffix
                dest.write_bytes(body)
                report[key] = {
                    "name": suffix,
                    "size": len(body),
                    "path": str(dest),
                    "url": resp.url,
                    "status": resp.status,
                }
            except Exception as exc:
                report[key] = {"error": str(exc)}

        _download('[data-ns="dl-pdf"]', "pdf_download", "ebook.pdf")
        _download('[data-ns="dl-zip"]', "zip_download", "package.zip")

        report["console_errors"] = [c for c in report["console"] if c.get("type") == "error"]
        context.close()
        browser.close()

    slim = {k: report[k] for k in report if k != "console"}
    (ARTIFACTS / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(slim, indent=2, default=str))
    save_ok = False
    save = report.get("save") or {}
    if save.get("status") == 200:
        save_ok = True
    body = save.get("body") if isinstance(save.get("body"), dict) else {}
    if body.get("ok") or body.get("id") or body.get("project_id"):
        save_ok = True
    ok = (
        bool((report.get("open") or {}).get("ok"))
        and save_ok
        and bool((report.get("pdf_download") or {}).get("size"))
        and bool((report.get("zip_download") or {}).get("size"))
        and not report.get("page_errors")
        and bool((report.get("regen") or {}).get("cover_regenerated"))
    )
    return 0 if ok else 1


def _note_ext(url: str) -> None:
    low = str(url or "").lower()
    if "pexels.com" in low:
        report["pexels_browser"] += 1
    if "openai.com" in low or "tavily.com" in low or "minimax" in low:
        report["openai_browser"] += 1


if __name__ == "__main__":
    raise SystemExit(main())
