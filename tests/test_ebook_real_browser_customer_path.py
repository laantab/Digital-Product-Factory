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
            stdin=subprocess.DEVNULL,
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

    # ------------------------------------------------------------------
    # ONE-BUTTON CUSTOMER PATH
    #
    # Migrated from the retired one-shot flow. Every customer guarantee the
    # old test made is still made here -- one project, understandable
    # progress, a real preview, a real PDF and ZIP, reopen without
    # regeneration, no leaked internals, zero paid calls. What changed is the
    # route the customer takes to them: one Build My Ebook click now drives
    # the workspace orchestrator instead of a single blocking generate.
    # ------------------------------------------------------------------

    #: Anything here on the customer's screen is a leak of internal operation.
    FORBIDDEN_SCREEN_TEXT = (
        "Confirm paid action",
        "Confirmation token",
        "Maximum total",
        "Per-chapter maximum",
        "Remaining:",
        "OpenAI",
        "Ollama",
        "Qwen",
        "Tavily",
        "Pexels",
        "Traceback",
        "ebook_workspace",
        "project_id",
        "approve_stage",
        "Approve & Save",
    )
    #: The ten-stage operational rail must never appear on the customer screen.
    RAIL_WORDS = ("Preflight", "Outline", "Manuscript", "Visuals", "Preview approval")

    def _screen(self, page) -> str:
        return page.locator("[data-view='ebook-build']").inner_text()

    def _assert_screen_is_customer_safe(self, page, *, where: str) -> None:
        text = self._screen(page)
        for needle in self.FORBIDDEN_SCREEN_TEXT:
            self.assertNotIn(needle, text, f"{where} showed internal text {needle!r}")
        for word in self.RAIL_WORDS:
            self.assertNotIn(word, text, f"{where} showed the operational rail ({word!r})")
        self.assertNotIn("{", text, f"{where} showed raw JSON")
        self.assertTrue(text.strip(), f"{where} was blank")

    def _project_rows(self, page) -> list:
        return page.evaluate(
            "fetch('/projects?admin=1').then(r => r.json())"
        )

    def test_21_step_container_gardening_customer_path(self):
        from playwright.sync_api import expect

        context = self.browser.new_context(accept_downloads=True)
        page = context.new_page()
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        build_starts = []
        advances = []

        def capture(response):
            if response.request.method != "POST":
                return
            url = response.url
            if url.rstrip("/").endswith("/ebook/build"):
                try:
                    build_starts.append(response.json())
                except Exception:
                    build_starts.append({})
            elif "/ebook/build/" in url and url.endswith("/advance"):
                advances.append(url)

        page.on("response", capture)

        # 1 The customer completes the ebook form.
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
        expect(form.locator("select[name='include_images']")).to_have_value("Yes")

        # 2 One click. The button says what it does.
        expect(page.locator("#factoryBtn")).to_have_text("Build My Ebook")
        page.click("#factoryBtn")

        # 4 The browser shows understandable progress on its own screen.
        page.wait_for_selector("[data-view='ebook-build']:not(.hidden)", timeout=30000)
        page.wait_for_selector("[data-ebook-build-bar]", timeout=30000)
        self._assert_screen_is_customer_safe(page, where="progress screen")
        progress_text = self._screen(page)
        # The eyebrow is styled uppercase, and the step message replaces the
        # plain-case copy within the first moment of a build, so the screen
        # legitimately reads "PREPARING YOUR EBOOK" by the time we look.
        self.assertIn("preparing your ebook", progress_text.lower())

        # 11 Refresh mid-generation resumes the same build safely.
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("[data-view='ebook-build']:not(.hidden)", timeout=30000)
        page.wait_for_selector("[data-ebook-build-bar]", timeout=30000)
        self._assert_screen_is_customer_safe(page, where="after refresh")

        # 5 The build reaches 100% with no further production clicks.
        page.wait_for_selector("[data-ebook-build-done]", timeout=600000)
        done_text = self._screen(page)
        self.assertIn("Your ebook is ready", done_text)
        self.assertIn("100%", done_text)
        self._assert_screen_is_customer_safe(page, where="finished screen")

        # 3 No production-stage clicks were needed: the only click was Build.
        #   Every stage after it was driven by the orchestrator poller.
        self.assertTrue(advances, "the orchestrator was never advanced")

        # 2 (cont.) Exactly one project exists, and a repeat click attaches.
        rows = self._project_rows(page)
        ebooks = [r for r in rows if r.get("type") == "ebook"]
        self.assertEqual(len(ebooks), 1, f"one click must create one project, got {len(ebooks)}")
        pid = ebooks[0]["id"]
        first_start = build_starts[0] if build_starts else {}
        self.assertEqual(int(first_start.get("project_id") or 0), int(pid))
        self.assertTrue(first_start.get("created"), first_start)

        # 7 The finished project is a DRAFT until the customer approves it.
        opened = page.evaluate(f"fetch('/projects/{pid}').then(r => r.json())")
        self.assertEqual((opened.get("data") or {}).get("artifact_state"), "DRAFT")

        # The five finished actions the customer needs are all present.
        for selector, label in (
            ("[data-ebook-open]", "Open Product"),
            ("[data-ebook-dl-pdf]", "Download PDF"),
            ("[data-ebook-dl-zip]", "Download ZIP"),
            ("[data-ebook-changes]", "Make Changes"),
            ("[data-ebook-approve]", "Approve Product"),
        ):
            expect(page.locator(selector)).to_have_text(label)

        before_reopen = _read_call_log(self.call_log)

        # 6 Preview opens, locally, and is clean.
        #   The book's title is the one the Factory approved at the title stage,
        #   not the raw string typed into the form, so assert against the
        #   persisted title. What must hold either way: a real title is shown,
        #   the leading colon the customer typed is gone, and nothing internal
        #   leaked into the page.
        status_now = page.evaluate(f"fetch('/ebook/build/{pid}/status').then(r => r.json())")
        preview_url = status_now.get("preview_url")
        book_title = (status_now.get("title") or "").strip()
        self.assertTrue(preview_url, "finished build exposed no preview")
        self.assertTrue(book_title, "finished build has no title")
        self.assertFalse(book_title.startswith(":"), f"stored title kept a leading colon: {book_title!r}")
        preview_page = context.new_page()
        preview_resp = preview_page.goto(self.base + preview_url, wait_until="domcontentloaded")
        self.assertEqual(preview_resp.status, 200)
        preview_html = html_lib.unescape(preview_page.content())
        self.assertIn(book_title, preview_html, "preview does not show the book's title")
        _assert_clean_text(self, preview_html, where="preview HTML")
        preview_page.close()

        # 7-8 PDF and ZIP download from the real buttons.
        net_log = []
        page.on("request", lambda r: net_log.append(f"{r.method} {r.url}"))

        try:
            with page.expect_response(
                lambda r: r.request.method == "GET" and r.url.split("?")[0].endswith("ebook.pdf"),
                timeout=90000,
            ) as pdf_info:
                page.locator("[data-ebook-dl-pdf]").click()
        except Exception:
            raise AssertionError("PDF button did not GET ebook.pdf. requests=" + repr(net_log[-20:]))
        pdf_resp = pdf_info.value
        self.assertEqual(pdf_resp.status, 200, pdf_resp.url)
        pdf_bytes = pdf_resp.body()
        self.assertTrue(pdf_bytes.startswith(b"%PDF"), "Downloaded PDF is not a PDF")
        self.assertGreater(len(pdf_bytes), 8000)
        (self.artifacts / "ebook.pdf").write_bytes(pdf_bytes)

        try:
            with page.expect_response(
                lambda r: r.request.method == "GET" and r.url.split("?")[0].endswith("package.zip"),
                timeout=90000,
            ) as zip_info:
                page.locator("[data-ebook-dl-zip]").click()
        except Exception:
            raise AssertionError("ZIP button did not GET package.zip. requests=" + repr(net_log[-20:]))
        zip_resp = zip_info.value
        self.assertEqual(zip_resp.status, 200, zip_resp.url)
        zip_bytes = zip_resp.body()
        self.assertTrue(zip_bytes.startswith(b"PK"), "Downloaded ZIP is not a ZIP")
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

        # The book itself is real, correctly titled, and free of leaked text.
        import fitz

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pdf_text = "\n".join(pg.get_text("text") or "" for pg in doc)
        for page_obj in doc:
            for link in page_obj.get_links() or []:
                uri = str(link.get("uri") or "")
                self.assertNotIn("127.0.0.1", uri)
                self.assertNotIn("localhost", uri)
        doc.close()
        _assert_clean_text(self, pdf_text, where="PDF text")
        self.assertIn(AUTHOR, pdf_text)
        self.assertIn(book_title, pdf_text, "the PDF does not carry the book's title")
        sheet = _contact_sheet(pdf_bytes, self.artifacts / "ebook_customer_path_contact_sheet.png")
        self.assertTrue(sheet.is_file())
        public_sheet = ROOT / "test-results" / "ebook_customer_path_contact_sheet.png"
        public_sheet.parent.mkdir(parents=True, exist_ok=True)
        public_sheet.write_bytes(sheet.read_bytes())
        os.environ["EBOOK_CONTACT_SHEET"] = str(public_sheet)

        # 9-10 Saved Projects reopens the SAME project, and reopening changes
        #      nothing: same manuscript, same PDF bytes, same package.
        manuscript_before = hashlib.sha256(
            ((opened.get("data") or {}).get("content") or "").encode("utf-8")
        ).hexdigest()

        # Approve Product is the customer's explicit acceptance and the thing
        # that files the book under Saved Projects. It must not regenerate
        # anything and must not promote the artifact out of DRAFT.
        page.locator("[data-ebook-approve]").click()
        page.wait_for_timeout(2500)
        approved = page.evaluate(f"fetch('/projects/{pid}').then(r => r.json())")
        approved_data = approved.get("data") or {}
        self.assertEqual(approved_data.get("artifact_state"), "DRAFT",
                         "approving must not promote the artifact out of DRAFT")
        self.assertEqual(
            hashlib.sha256((approved_data.get("content") or "").encode("utf-8")).hexdigest(),
            manuscript_before,
            "approving regenerated the manuscript",
        )

        page.evaluate("go('dashboard')")
        page.evaluate("go('saved')")
        page.wait_for_selector("#savedList", timeout=30000)
        expect(page.locator("#savedList")).to_contain_text("Container Gardening", timeout=30000)
        page.locator("#savedList").get_by_role("button", name="Open").first.evaluate("el => el.click()")
        page.wait_for_selector("[data-ebook-build-done]", timeout=60000)
        self._assert_screen_is_customer_safe(page, where="reopened screen")

        reopened = page.evaluate(f"fetch('/projects/{pid}').then(r => r.json())")
        reopened_data = reopened.get("data") or {}
        self.assertEqual(
            hashlib.sha256((reopened_data.get("content") or "").encode("utf-8")).hexdigest(),
            manuscript_before,
            "Reopening regenerated the manuscript",
        )
        self.assertEqual(reopened_data.get("artifact_state"), "DRAFT")
        rows_after = self._project_rows(page)
        self.assertEqual(
            len([r for r in rows_after if r.get("type") == "ebook"]),
            1,
            "reopening created a second project",
        )

        with page.expect_response(
            lambda r: r.request.method == "GET" and r.url.split("?")[0].endswith("ebook.pdf"),
            timeout=90000,
        ) as pdf2_info:
            page.locator("[data-ebook-dl-pdf]").click()
        self.assertEqual(
            hashlib.sha256(pdf2_info.value.body()).hexdigest(),
            hashlib.sha256(pdf_bytes).hexdigest(),
            "Reopening changed the PDF bytes",
        )

        # 12 No internal cost / provider / error language anywhere on screen.
        self._assert_screen_is_customer_safe(page, where="final screen")
        self.assertFalse(
            [e for e in console_errors if "favicon" not in e.lower()],
            f"browser console errors: {console_errors[:5]}",
        )

        # 15 Zero external or paid calls, for the whole journey and for the
        #    reopen/download half specifically.
        after = _read_call_log(self.call_log)
        self.assertEqual(after.get("paid"), before_reopen.get("paid"))
        self.assertEqual(after.get("pexels_http"), before_reopen.get("pexels_http"))
        self.assertEqual(int(after.get("paid") or 0), 0)
        context.close()

    def test_22_repeat_build_click_attaches_to_the_same_project(self):
        """A second Build click must attach, never create a second project."""
        context = self.browser.new_context()
        page = context.new_page()
        page.goto(self.base + "/", wait_until="domcontentloaded")

        fields = {
            "ebook_title": "Duplicate Protection Check",
            "author_brand": AUTHOR,
            "topic": "duplicate protection",
            "audience": "testers",
            "chapters": "2",
            "include_images": "No",
        }
        script = (
            "fetch('/ebook/build', {method:'POST',"
            "headers:{'Content-Type':'application/json'},"
            "body: JSON.stringify({fields: %s})}).then(r => r.json())" % json.dumps(fields)
        )
        first = page.evaluate(script)
        second = page.evaluate(script)
        self.assertTrue(first.get("created"), first)
        self.assertFalse(second.get("created"), second)
        self.assertEqual(first.get("project_id"), second.get("project_id"))
        context.close()

    def test_23_other_product_builders_keep_their_own_flow(self):
        """Only ebook routes to the build screen. Other builders are untouched."""
        from playwright.sync_api import expect

        context = self.browser.new_context()
        page = context.new_page()
        page.goto(self.base + "/", wait_until="domcontentloaded")
        page.evaluate("go('factory')")
        page.wait_for_selector("#factoryTypes")

        for ftype in ("word_search", "crossword", "math_worksheet", "coloring_book"):
            button = page.locator(f"button[data-ft='{ftype}']")
            if button.count() == 0:
                continue
            button.click()
            page.wait_for_selector("#factoryForm")
            # The shared Generate button keeps its own label and its own path.
            expect(page.locator("#factoryBtn")).to_have_text("Generate Product")
            self.assertTrue(
                page.locator("[data-view='ebook-build']").get_attribute("class").find("hidden") >= 0,
                f"{ftype} must not open the ebook build screen",
            )
        # And selecting ebook again restores the one-button label.
        page.locator("button[data-ft='ebook']").click()
        page.wait_for_selector("#factoryForm input[name='ebook_title']")
        expect(page.locator("#factoryBtn")).to_have_text("Build My Ebook")
        context.close()


if __name__ == "__main__":
    unittest.main()
