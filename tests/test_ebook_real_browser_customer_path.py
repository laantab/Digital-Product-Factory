"""Real-browser factory ebook customer path. Isolated DB and exports.

Flask test-client is not a substitute. Zero paid/OpenAI/Tavily/MiniMax calls.
"""
from __future__ import annotations

import hashlib
import html as html_lib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("FACTORY_TEST_MODE", "1")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("TAVILY_API_KEY", "")
os.environ.setdefault("AI_INTEGRATIONS_OPENAI_API_KEY", "")
os.environ.setdefault("PEXELS_API_KEY", "")

TITLE = "Beginner's Guide to Container Gardening"
AUTHOR = "Lonnie Brown"
CONTAMINATION_NEEDLES = (
    "401 Client",
    "Unauthorized",
    "Retry missing image",
    "Digital Product Factory",
    "127.0.0.1",
    "localhost",
    "api.pexels.com",
    "Choose cover photo",
    "Traceback",
)


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


def _read_call_log(path: Path) -> dict:
    if not path.is_file():
        return {"paid": 0, "pexels_http": 0}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"paid": 0, "pexels_http": 0}


def _assert_clean_text(self: unittest.TestCase, blob: str, *, where: str) -> None:
    low = html_lib.unescape(blob or "")
    self.assertNotIn(": Beginner", low, f"{where} has a leading-colon title")
    self.assertNotIn("A practical, beginner-friendly handbook for growing vegetables and herbs in pots", low)
    for needle in CONTAMINATION_NEEDLES:
        self.assertNotIn(needle, low, f"{where} contains {needle!r}")


def _contact_sheet(pdf_bytes: bytes, dest: Path) -> Path:
    import fitz
    from PIL import Image

    dest.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    count = min(doc.page_count, 8)
    images = []
    for i in range(count):
        pix = doc[i].get_pixmap(matrix=fitz.Matrix(1.2, 1.2), alpha=False)
        images.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
    doc.close()
    if not images:
        raise AssertionError("PDF has no pages to inspect")
    w = max(im.width for im in images)
    h = max(im.height for im in images)
    cols = 4
    rows = (len(images) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * h), (255, 255, 255))
    for idx, im in enumerate(images):
        sheet.paste(im, ((idx % cols) * w, (idx // cols) * h))
    sheet.save(dest, format="PNG")
    return dest


class EbookRealBrowserCustomerPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright

        cls._tmp = tempfile.TemporaryDirectory(prefix="ebook_browser_")
        tmp = Path(cls._tmp.name)
        cls.db_path = tmp / "projects.db"
        cls.exports_dir = tmp / "exports"
        cls.artifacts = tmp / "artifacts"
        cls.call_log = tmp / "call_log.json"
        cls.exports_dir.mkdir()
        cls.artifacts.mkdir()
        cls.call_log.write_text(json.dumps({"paid": 0, "pexels_http": 0}), encoding="utf-8")
        cls.port = _free_port()
        cls.base = f"http://127.0.0.1:{cls.port}"
        env = os.environ.copy()
        env.update(
            {
                "FACTORY_TEST_MODE": "1",
                "EBOOK_CUSTOMER_PATH_FIXTURE": "1",
                "FACTORY_DB_PATH": str(cls.db_path),
                "FACTORY_EXPORTS_DIR": str(cls.exports_dir),
                "FACTORY_CALL_LOG": str(cls.call_log),
                "FACTORY_PORT": str(cls.port),
                "OPENAI_API_KEY": "",
                "TAVILY_API_KEY": "",
                "AI_INTEGRATIONS_OPENAI_API_KEY": "",
                "MINIMAX_API_KEY": "",
                "PEXELS_API_KEY": "",
                "PYTHONUNBUFFERED": "1",
            }
        )
        cls.proc = subprocess.Popen(
            [sys.executable, str(ROOT / "tests" / "_isolated_ebook_server.py")],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        started = False
        deadline = time.time() + 60
        buf = []
        while time.time() < deadline:
            line = cls.proc.stdout.readline() if cls.proc.stdout else ""
            if line:
                buf.append(line)
                if "FACTORY_STARTED" in line:
                    started = True
                    break
            elif cls.proc.poll() is not None:
                break
        if not started:
            rest = cls.proc.stdout.read() if cls.proc.stdout else ""
            cls.proc.kill()
            raise RuntimeError("Isolated ebook Flask server failed to start:\n" + "".join(buf) + rest)
        # Keep draining stdout or the PIPE buffer fills and Flask deadlocks
        # while logging /download requests (PDF/ZIP then never complete).
        def _drain():
            try:
                while cls.proc.stdout and cls.proc.poll() is None:
                    if not cls.proc.stdout.readline():
                        break
            except Exception:
                pass

        cls._drain = __import__("threading").Thread(target=_drain, daemon=True)
        cls._drain.start()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.browser.close()
        except Exception:
            pass
        try:
            cls.playwright.stop()
        except Exception:
            pass
        if getattr(cls, "proc", None) and cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=8)
            except Exception:
                cls.proc.kill()
        try:
            cls._tmp.cleanup()
        except Exception:
            pass

    def test_21_step_container_gardening_customer_path(self):
        from playwright.sync_api import expect

        context = self.browser.new_context(accept_downloads=True)
        page = context.new_page()
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        gen_payload = {}
        regen_payloads = []

        def capture(response):
            url = response.url
            if response.request.method != "POST":
                return
            try:
                data = response.json()
            except Exception:
                return
            if url.endswith("/generate-product"):
                gen_payload.update(data)
            elif url.endswith("/ebook/regenerate-cover"):
                regen_payloads.append(data)

        page.on("response", capture)

        # 1-2 Open Factory → Ebook
        page.goto(self.base + "/", wait_until="domcontentloaded")
        page.evaluate("go('factory')")
        page.wait_for_selector("#factoryTypes")
        page.locator("button[data-ft='ebook']").click()
        page.wait_for_selector("#factoryForm input[name='ebook_title']")
        form = page.locator("#factoryForm")
        form.locator("input[name='ebook_title']").fill(": Beginner’s Guide to Container Gardening")
        form.locator("input[name='author_brand']").fill(AUTHOR)
        form.locator("input[name='topic']").fill("container gardening")
        form.locator("input[name='audience']").fill("Beginners growing food in pots")
        form.locator("input[name='chapters']").fill("6")
        select = form.locator("select[name='include_images']")
        expect(select).to_have_value("Yes")

        # 5 Generate
        page.click("#factoryBtn")
        page.get_by_role("button", name="Approve & Save").wait_for(timeout=180000)

        # 6-7 No raw error / valid cover
        html = page.locator("#ebookPreviewFrame").get_attribute("srcdoc") or ""
        self.assertTrue(html, "Formatted preview did not render")
        _assert_clean_text(self, html, where="preview HTML")
        plain = html_lib.unescape(html)
        self.assertIn(TITLE, plain)
        self.assertIn(AUTHOR, plain)
        self.assertIn('id="chapter-1"', html)
        self.assertIn('href="#chapter-1"', html)
        self.assertIn("Why Container Gardening Works for Beginners", html)
        self.assertTrue(gen_payload.get("ebook_ready"), gen_payload.get("next_action") or gen_payload.get("contamination"))
        cover = gen_payload.get("cover_design") or {}
        self.assertTrue(cover.get("selected_layout"), "Cover was not auto-selected")
        self.assertFalse(cover.get("generic_template"))
        first_sha = str((cover.get("source") or {}).get("sha256") or "")
        self.assertTrue(first_sha)

        # 8-9 Regenerate cover → different valid candidate
        page.locator('[data-ns="regen-cover"]').first.evaluate("el => el.click()")
        page.wait_for_timeout(1500)
        deadline = time.time() + 120
        while time.time() < deadline and not regen_payloads:
            page.wait_for_timeout(250)
        self.assertTrue(regen_payloads, "Regenerate Cover did not return a payload")
        first_regen = regen_payloads[-1]
        self.assertTrue(first_regen.get("cover_regenerated"), first_regen)
        second_sha = str(((first_regen.get("cover") or {}).get("source") or {}).get("sha256") or "")
        self.assertTrue(second_sha)
        self.assertNotEqual(second_sha, first_sha, "Regenerated cover reused the previous photograph")

        # 10 Simulate regen failure — prior cover survives
        page.route(
            "**/ebook/regenerate-cover",
            lambda route: route.continue_(
                post_data=json.dumps(
                    {
                        **(json.loads(route.request.post_data or "{}") or {}),
                        "simulate_failure": True,
                    }
                )
            ),
        )
        page.locator('[data-ns="regen-cover"]').first.evaluate("el => el.click()")
        page.wait_for_timeout(1500)
        fail_row = regen_payloads[-1]
        self.assertFalse(fail_row.get("cover_regenerated"))
        self.assertIn("kept", str(fail_row.get("message") or "").lower())
        page.unroute("**/ebook/regenerate-cover")

        html = page.locator("#ebookPreviewFrame").get_attribute("srcdoc") or ""
        self.assertTrue(html, "Preview missing after cover regenerate")
        _assert_clean_text(self, html, where="preview HTML after cover")

        # 11 Approve All Visuals
        page.locator("[data-approve-all-visuals]").first.evaluate("el => el.click()")
        expect(page.locator("#toast")).to_contain_text("Visuals approved")

        # 12-14 Preview already shown; Approve & Save; visible success
        with page.expect_response(
            lambda r: r.url.rstrip("/").endswith("/ebook/save") and r.request.method == "POST",
            timeout=60000,
        ) as save_info:
            page.locator('[data-ns="save"]').first.evaluate("el => el.click()")
        save_resp = save_info.value
        self.assertEqual(save_resp.status, 200, save_resp.text())
        save_body = save_resp.json()
        self.assertTrue(save_body.get("ok") or save_body.get("id"), save_body)
        page.locator("#toast").filter(has_text="Project saved successfully").wait_for(timeout=15000)

        # 15-16 Navigate away and reopen Saved Projects
        page.evaluate("typeof go === 'function' && go('dashboard')")
        with page.expect_response(
            lambda r: "/projects?" in r.url and r.request.method == "GET",
            timeout=30000,
        ) as list_info:
            page.evaluate("typeof go === 'function' && go('saved')")
        listed = []
        try:
            listed = list_info.value.json()
        except Exception:
            listed = []
        self.assertTrue(
            any("Container Gardening" in str((row or {}).get("name") or "") for row in listed),
            listed,
        )
        page.wait_for_selector("#savedList")
        expect(page.locator("#savedList")).to_contain_text("Container Gardening", timeout=30000)
        before_reopen = _read_call_log(self.call_log)
        before_reopen = _read_call_log(self.call_log)

        # 17 Open exact artifact
        page.locator("#savedList").get_by_role("button", name="Open").first.evaluate("el => el.click()")
        page.locator('[data-ns="dl-pdf"]').first.wait_for(timeout=30000)
        reopened_html = page.locator("#ebookPreviewFrame").get_attribute("srcdoc") or ""
        self.assertEqual(
            hashlib.sha256(html.encode("utf-8")).hexdigest(),
            hashlib.sha256(reopened_html.encode("utf-8")).hexdigest(),
            "Reopened preview HTML is not the same accepted artifact",
        )

        # 18-20 Download PDF and ZIP from the real buttons. Capture the GET
        # bodies in Python — triggerDownload uses fetch+blob, so expect_download
        # never fires, and page.evaluate(Array.from(Uint8Array)) times out.
        pkg = str(
            ((save_body.get("project") or {}).get("data") or {}).get("package_id")
            or gen_payload.get("package_id")
            or ""
        )
        self.assertTrue(pkg, "Saved ebook is missing package_id")
        net_log = []
        page.on("request", lambda r: net_log.append(f"{r.method} {r.url}"))

        def _export_get(url: str, filename: str) -> bool:
            path = (url or "").split("?")[0]
            return path.endswith("/" + filename) or path.endswith(filename)

        try:
            with page.expect_response(
                lambda r: r.request.method == "GET" and _export_get(r.url, "ebook.pdf"),
                timeout=90000,
            ) as pdf_info:
                page.locator('[data-ns="dl-pdf"]').first.evaluate("el => el.click()")
        except Exception:
            raise AssertionError("PDF button did not GET ebook.pdf. requests=" + repr(net_log[-20:]))
        pdf_resp = pdf_info.value
        self.assertEqual(pdf_resp.status, 200, pdf_resp.url)
        pdf_bytes = pdf_resp.body()
        pdf_path = self.artifacts / "ebook.pdf"
        pdf_path.write_bytes(pdf_bytes)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"), "Downloaded PDF is not a PDF")
        self.assertGreater(len(pdf_bytes), 8000)
        self.assertIn(f"/download/{pkg}/ebook.pdf", pdf_resp.url)

        try:
            with page.expect_response(
                lambda r: r.request.method == "GET" and _export_get(r.url, "package.zip"),
                timeout=90000,
            ) as zip_info:
                page.locator('[data-ns="dl-zip"]').first.evaluate("el => el.click()")
        except Exception:
            raise AssertionError("ZIP button did not GET package.zip. requests=" + repr(net_log[-20:]))
        zip_resp = zip_info.value
        self.assertEqual(zip_resp.status, 200, zip_resp.url)
        zip_bytes = zip_resp.body()
        zip_path = self.artifacts / "package.zip"
        zip_path.write_bytes(zip_bytes)
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = set(zf.namelist())
            self.assertIn("ebook.pdf", names)
            self.assertIn("ebook.html", names)
            zip_pdf = zf.read("ebook.pdf")
            zip_html = zf.read("ebook.html").decode("utf-8", errors="replace")
        self.assertEqual(hashlib.sha256(pdf_bytes).hexdigest(), hashlib.sha256(zip_pdf).hexdigest())
        _assert_clean_text(self, zip_html, where="ZIP HTML")

        import fitz

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pdf_text = "\n".join(page.get_text("text") or "" for page in doc)
        for page_obj in doc:
            for link in page_obj.get_links() or []:
                uri = str(link.get("uri") or "")
                self.assertNotIn("127.0.0.1", uri)
                self.assertNotIn("localhost", uri)
        doc.close()
        _assert_clean_text(self, pdf_text, where="PDF text")
        self.assertIn("Why Container Gardening Works for Beginners", pdf_text)
        self.assertIn(AUTHOR, pdf_text)
        sheet = _contact_sheet(pdf_bytes, self.artifacts / "ebook_customer_path_contact_sheet.png")
        self.assertTrue(sheet.is_file())
        # Keep a copy under flask_app/test-results for the passing report.
        public_sheet = ROOT / "test-results" / "ebook_customer_path_contact_sheet.png"
        public_sheet.parent.mkdir(parents=True, exist_ok=True)
        public_sheet.write_bytes(sheet.read_bytes())
        os.environ["EBOOK_CONTACT_SHEET"] = str(public_sheet)

        # 21 Reopen/download made no provider calls
        after = _read_call_log(self.call_log)
        self.assertEqual(after.get("paid"), before_reopen.get("paid"))
        self.assertEqual(after.get("pexels_http"), before_reopen.get("pexels_http"))
        self.assertEqual(int(after.get("paid") or 0), 0)
        context.close()


if __name__ == "__main__":
    unittest.main()
