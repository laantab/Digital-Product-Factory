"""Saved Open must keep the latest customer choice through slow/failed reads."""
import hashlib
import socket
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_saved_products_bounded_loading import isolated_env

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def saved_browser(tmp_path):
    from playwright.sync_api import sync_playwright
    from tests.test_ebook_real_browser_customer_path import EbookRealBrowserCustomerPathTests

    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    env = isolated_env(tmp_path)
    script = ("from tests._isolated_saved_server import seed,app; "
              "seed(count=2,size=2000); "
              f"app.run(host='127.0.0.1',port={port},threaded=True,use_reloader=False)")
    with (tmp_path / 'server.log').open('w') as log:
        process = subprocess.Popen([sys.executable, '-c', script], cwd=ROOT,
                                   env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            with socket.socket() as sock:
                if sock.connect_ex(('127.0.0.1', port)) == 0:
                    break
            assert process.poll() is None, (tmp_path / 'server.log').read_text()
            time.sleep(.1)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            fixture = SimpleNamespace(browser=browser, ASSETS=EbookRealBrowserCustomerPathTests.ASSETS)
            context = EbookRealBrowserCustomerPathTests._new_context(fixture)
            page = context.new_page()
            page.add_init_script("""
                window.detailReads = 0;
                const originalFetch = window.fetch;
                window.fetch = async (...args) => {
                    const detail = /\\/projects\\/\\d+$/.test(String(args[0]));
                    if (detail) window.detailReads++;
                    try { return await originalFetch(...args); }
                    finally { if (detail) window.detailReads--; }
                };
            """)
            page.goto(f'http://127.0.0.1:{port}')
            records = page.request.get(f'http://127.0.0.1:{port}/projects?limit=10').json()
            full = [page.request.get(f'http://127.0.0.1:{port}/projects/{p["id"]}').json()
                    for p in sorted(records, key=lambda p: p['name'])]
            files_before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in (tmp_path / 'exports').rglob('*') if p.is_file()}
            page.locator('#nav [data-go="saved"]').click()
            page.locator('#savedList [data-open]').nth(1).wait_for()
            yield page, full
            for original in full:
                after = page.request.get(f'http://127.0.0.1:{port}/projects/{original["id"]}').json()
                assert after['data'] == original['data'], 'Open must preserve the stored product'
            assert {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (tmp_path / 'exports').rglob('*') if p.is_file()} == files_before
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=10)


def open_button(page, name):
    return page.locator('#savedList > div').filter(has_text=name).locator('[data-open]')


def settle(page):
    page.wait_for_function('window.detailReads === 0')
    page.evaluate('() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')


def test_opening_finished_product_does_not_save_or_rebuild_it(saved_browser):
    page, (first, _) = saved_browser
    writes = []
    page.on('request', lambda r: writes.append((r.method, r.url))
            if r.method in ('POST', 'PUT', 'PATCH', 'DELETE') else None)
    open_button(page, first['name']).click()
    page.locator('#factoryOutput').get_by_role('heading', name=first['name'], exact=True).wait_for()
    settle(page)
    assert not writes, 'Reopening existing files must not trigger Save or Export'


def test_late_open_cannot_replace_the_more_recently_selected_saved_product(saved_browser):
    page, (first, second) = saved_browser
    held = []
    page.route(f'**/projects/{first["id"]}', lambda route: held.append(route), times=1)
    open_button(page, first['name']).click()
    page.wait_for_function('window.detailReads === 1')
    open_button(page, second['name']).click()
    page.locator('#factoryOutput').get_by_role('heading', name=second['name'], exact=True).wait_for()
    held[0].fulfill(json=first)
    settle(page)
    assert page.locator('#factoryOutput').get_by_role('heading', name=second['name'], exact=True).is_visible()


def test_leaving_saved_projects_does_not_get_undone_by_a_late_open(saved_browser):
    page, (first, _) = saved_browser
    held = []
    page.route(f'**/projects/{first["id"]}', lambda route: held.append(route), times=1)
    open_button(page, first['name']).click()
    page.wait_for_function('window.detailReads === 1')
    page.locator('#nav [data-go="dashboard"]').click()
    held[0].fulfill(json=first)
    settle(page)
    assert page.evaluate('current') == 'dashboard'


@pytest.mark.parametrize('response', ['unavailable', 'malformed', 'wrong_product'])
def test_failed_saved_open_keeps_the_list_and_allows_retry(saved_browser, response):
    page, (first, second) = saved_browser
    def fail(route):
        if response == 'unavailable':
            route.fulfill(status=503, json={'error': 'Temporarily unavailable'})
        elif response == 'malformed':
            route.fulfill(status=200, json={})
        else:
            route.fulfill(status=200, json=second)
    page.route(f'**/projects/{first["id"]}', fail, times=1)
    open_button(page, first['name']).click()
    settle(page)
    assert page.evaluate('current') == 'saved'
    assert 'Could not open' in page.locator('#toast').inner_text()
    open_button(page, first['name']).click()
    page.locator('#factoryOutput').get_by_role('heading', name=first['name'], exact=True).wait_for()
    assert page.locator('#factoryForm [name="pages"]').input_value() == '2'


def test_stalled_saved_open_times_out_and_the_same_product_can_be_retried(saved_browser):
    page, (first, _) = saved_browser
    page.clock.install()
    held = []
    page.route(f'**/projects/{first["id"]}', lambda route: held.append(route), times=1)
    open_button(page, first['name']).click()
    page.wait_for_function('window.detailReads === 1')
    page.clock.fast_forward(31000)
    assert 'Could not open' in page.locator('#toast').inner_text()
    assert page.evaluate('current') == 'saved'
    open_button(page, first['name']).click()
    page.locator('#factoryOutput').get_by_role('heading', name=first['name'], exact=True).wait_for()
    held[0].fulfill(json=first)


@pytest.mark.parametrize("finished", [True, False])
def test_saved_ebook_open_never_advances_or_resumes_a_build(saved_browser, finished):
    import copy
    page, (original, _) = saved_browser
    full = copy.deepcopy(original)
    full["type"] = "ebook"
    full["data"] = {"title": original["name"], "ebook_build": {"finished": True}}
    page.route(f'**/projects/{original["id"]}', lambda r: r.fulfill(json=full), times=1)
    status = {"ok": True, "project_id": original["id"], "title": original["name"],
              "finished": finished, "failed": False, "percent": 100 if finished else 90,
              "activity": {"state": "done" if finished else "stalled"},
              "downloads": {"pdf": "/existing.pdf", "zip": "/existing.zip"}}
    page.route(f'**/ebook/build/{original["id"]}/status', lambda r: r.fulfill(json=status))
    writes = []
    def mutation(route):
        writes.append(route.request.url)
        route.fulfill(json=status)
    page.route(f'**/ebook/build/{original["id"]}/advance', mutation)
    page.route(f'**/ebook/build/{original["id"]}/resume', mutation)
    page.clock.install()
    open_button(page, original["name"]).click()
    page.locator("#ebookBuildRoot h2").wait_for()
    page.clock.fast_forward(15000)
    page.evaluate('() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')
    assert writes == [], "Open must only read; Continue is a separate action"
    if finished:
        assert page.locator("[data-ebook-dl-pdf]").is_visible()
        assert page.locator("[data-ebook-dl-zip]").is_visible()
    else:
        assert page.locator("[data-ebook-resume]").is_visible()


def test_saved_export_review_exposes_existing_files_without_a_rebuild(saved_browser):
    import copy
    page, (original, _) = saved_browser
    full = copy.deepcopy(original)
    full['type'] = 'ebook'
    full['data'] = {'title': original['name'], 'ebook_build': {'finished': True}}
    page.route(f'**/projects/{original["id"]}', lambda r: r.fulfill(json=full), times=1)
    status = {'ok': True, 'project_id': original['id'], 'title': original['name'],
              'finished': False, 'failed': True, 'needs_export_review': True, 'saved_version_ready': True, 'percent': 90,
              'review_url': '/ebook-workspace/1/release-review',
              'saved_downloads': {'pdf': '/download/preserved/ebook.pdf', 'zip': '/download/preserved/package.zip'}}
    page.route(f'**/ebook/build/{original["id"]}/status', lambda r: r.fulfill(json=status))
    writes = []
    page.on('request', lambda req: writes.append(req.url) if '/ebook/build/' in req.url and req.method == 'POST' else None)
    open_button(page, original['name']).click()
    page.get_by_role('link', name='Review saved book').wait_for()
    assert page.get_by_role('link', name='Download saved PDF').get_attribute('href') == '/download/preserved/ebook.pdf'
    assert page.get_by_role('link', name='Download saved ZIP').get_attribute('href') == '/download/preserved/package.zip'
    assert page.locator('[data-ebook-resume]').count() == 0
    assert page.locator('[data-ebook-build-bar]').get_attribute('aria-valuenow') == '100'
    assert 'reviewed version is ready to download' in page.locator('[data-ebook-build-message]').inner_text()
    assert not writes
