"""Actual browser: queued build, refresh, finished exports. Local providers only."""
import io
import os
import socket
import subprocess
import sys
import time
import zipfile
from pathlib import Path

from pypdf import PdfReader
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def test_coloring_build_survives_browser_refresh_and_downloads(tmp_path):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    exports = tmp_path / 'exports'
    exports.mkdir()
    env = os.environ.copy()
    env.update({'FACTORY_TEST_MODE': '1', 'FACTORY_EXECUTION_MODE': 'workflow',
                'FACTORY_WORKFLOW_TASK': 'fixture/build_ebook', 'RENDER_API_KEY': 'fixture-only',
                'FACTORY_PUBLISH_EXPORTS': '1', 'COLORING_BROWSER_ROOT': str(tmp_path),
                'COLORING_BROWSER_PORT': str(port), 'FACTORY_DB_PATH': str(tmp_path/'projects.db'),
                'FACTORY_EXPORTS_DIR': str(exports), 'FLASK_EXPORTS_DIR': str(exports),
                'FACTORY_INVITE_CODE': '', 'SECRET_KEY': 'isolated-test-only',
                'OPENAI_API_KEY': '', 'AI_INTEGRATIONS_OPENAI_API_KEY': '', 'TAVILY_API_KEY': '', 'PEXELS_API_KEY': ''})
    with (tmp_path/'server.log').open('w') as output:
        proc = subprocess.Popen([sys.executable, str(ROOT/'tests/_isolated_coloring_server.py')], cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic()+30
        while time.monotonic() < deadline:
            with socket.socket() as sock:
                if sock.connect_ex(('127.0.0.1', port)) == 0:
                    break
            if proc.poll() is not None:
                raise AssertionError((tmp_path/'server.log').read_text())
            time.sleep(.2)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            from types import SimpleNamespace
            from tests.test_ebook_real_browser_customer_path import EbookRealBrowserCustomerPathTests
            fixture = SimpleNamespace(browser=browser, ASSETS=EbookRealBrowserCustomerPathTests.ASSETS)
            context = EbookRealBrowserCustomerPathTests._new_context(fixture, accept_downloads=True)
            page = context.new_page()
            page.goto(f'http://127.0.0.1:{port}')
            page.locator('#nav [data-go="factory"]').click()
            page.locator('[data-ft="coloring_book"]').click()
            page.locator('#factoryForm [name="coloring_title"]').fill('Deep water sea creatures')
            page.locator('#factoryForm [name="theme"]').fill('Deep water sea creatures')
            page.locator('#factoryForm [name="pages"]').fill('12')
            page.locator('#factoryBtn').click()
            page.locator('#factoryOutput').get_by_text('You can leave this page and return.', exact=False).wait_for(timeout=15000)
            pid = page.evaluate('localStorage.getItem("factoryColoringBuild")')
            assert pid
            page.reload()
            page.locator('#nav [data-go="factory"]').click()
            page.locator('#factoryOutput [data-preview-dl-pdf]').wait_for(timeout=120000)
            assert page.locator('#factoryForm [name="pages"]').input_value() == '12'
            assert page.locator('#factoryForm [name="theme"]').input_value() == 'Deep water sea creatures'
            with page.expect_download() as event:
                page.locator('#factoryOutput [data-preview-dl-pdf]').click()
            pdf = Path(event.value.path()).read_bytes()
            assert len(PdfReader(io.BytesIO(pdf)).pages) == 13
            saved = page.request.get(f'http://127.0.0.1:{port}/coloring/build/{pid}/status').json()
            assert saved['finished']
            url = saved['result']['product_exports']['files']['zip']['url']
            package = page.request.get(f'http://127.0.0.1:{port}{url}').body()
            with zipfile.ZipFile(io.BytesIO(package)) as archive:
                assert any(archive.read(n) == pdf for n in archive.namelist() if n.endswith('.pdf'))
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=15)
