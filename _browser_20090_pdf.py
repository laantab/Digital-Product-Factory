"""Capture the live PDF download for project 20090."""
from pathlib import Path

from playwright.sync_api import sync_playwright

ART = Path("test-results/ebook_20090_browser")
ART.mkdir(parents=True, exist_ok=True)


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("http://127.0.0.1:5055", wait_until="networkidle")
        page.wait_for_function("typeof go === 'function'")
        page.evaluate("go('saved')")
        page.wait_for_selector("#savedList [data-open]", timeout=15000)
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
        page.wait_for_timeout(1500)
        with page.expect_response(
            lambda r: r.url.endswith("ebook.pdf") and r.status == 200,
            timeout=300000,
        ) as info:
            if page.locator("[data-preview-dl-pdf]").count():
                page.locator("[data-preview-dl-pdf]").first.evaluate("el => el.click()")
            else:
                page.locator('[data-ns="dl-pdf"]').first.evaluate("el => el.click()")
        resp = info.value
        body = resp.body()
        dest = ART / "ebook.pdf"
        dest.write_bytes(body)
        print("pdf", resp.status, len(body), dest)
        browser.close()
    return 0 if dest.stat().st_size > 1000 else 1


if __name__ == "__main__":
    raise SystemExit(main())
