"""The manuscript review controls must preserve safe review and rejection."""
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
import copy
import json
import pytest
from tests.test_ebook_manuscript_editor import draft

ROOT = Path(__file__).resolve().parents[1]


def test_editor_renders_original_proposal_and_reject_controls():
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")),
                      autoescape=select_autoescape(["html"]))
    page = env.get_template("ebook_manuscript_editor.html").render(
        project_id=42, manuscript="Safe draft.", manuscript_digest="digest")
    assert 'id="comparison"' in page
    assert 'id="before"' in page
    assert 'id="after"' in page
    assert 'id="reject"' in page
    assert "reviewed.original" in page
    assert "reviewed.edited" in page
    assert "nothing saved" in page
    assert "apply',{manuscript:reviewed.edited}" in page
    assert "action('undo')" in page


@pytest.fixture
def editor_browser(draft, monkeypatch):
    import database
    from app import app
    from services.jobs import store
    from playwright.sync_api import sync_playwright
    monkeypatch.setattr(store, 'get_for_project', lambda pid: None)
    project = database.create_project('Review controls', 'ebook', draft, system_test=True)
    client = app.test_client()
    path = f"/ebook-workspace/{project['id']}/edit-manuscript"
    requests = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 390, 'height': 844})
        def handle(route):
            request = route.request
            body = json.loads(request.post_data) if request.post_data else None
            if body:
                requests.append(body['action'])
            response = client.open(path, method=request.method, json=body)
            route.fulfill(status=response.status_code, body=response.data,
                          content_type=response.content_type)
        page.route('http://editor.test/**', handle)
        page.goto('http://editor.test' + path)
        yield page, project['id'], client, path, requests
        browser.close()


def test_browser_compare_reject_preserves_the_complete_saved_record(editor_browser):
    import database
    from playwright.sync_api import expect
    page, pid, _, _, requests = editor_browser
    before = copy.deepcopy(database.get_project(pid))
    original = before['data']['content']
    proposed = original + '\n\nCheck the backup camera before the event.\n'
    page.locator('#draft').fill(proposed)
    page.locator('#review').click()
    expect(page.locator('#comparison')).to_be_visible()
    expect(page.locator('#before')).to_have_text(original)
    expect(page.locator('#after')).to_have_text(proposed)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('#reject').click()
    expect(page.locator('#draft')).to_have_value(original)
    expect(page.locator('#apply')).to_be_disabled()
    expect(page.locator('#comparison')).to_be_hidden()
    assert requests == ['preview']
    assert database.get_project(pid) == before


def test_browser_typing_during_review_cannot_be_overwritten_by_late_response(editor_browser):
    import database
    from playwright.sync_api import expect
    page, pid, _, _, requests = editor_browser
    before = copy.deepcopy(database.get_project(pid))
    page.evaluate('''() => {
      const originalFetch = window.fetch;
      window.fetch = async (...args) => {
        const response = await originalFetch(...args);
        return new Promise(resolve => { window.releaseReview = () => resolve(response); });
      };
    }''')
    page.locator('#suggest').click()
    page.wait_for_function('typeof window.releaseReview === "function"')
    latest = before['data']['content'] + '\n\nKeep this newer sentence.\n'
    page.locator('#draft').fill(latest)
    page.evaluate('window.releaseReview()')
    expect(page.locator('#suggest')).to_be_enabled()
    expect(page.locator('#draft')).to_have_value(latest)
    expect(page.locator('#apply')).to_be_disabled()
    expect(page.locator('#comparison')).to_be_hidden()
    assert requests == ['preview']
    assert database.get_project(pid) == before


def test_browser_failed_review_keeps_draft_and_allows_retry(editor_browser):
    import database
    from playwright.sync_api import expect
    page, pid, _, _, _ = editor_browser
    before = copy.deepcopy(database.get_project(pid))
    proposed = before['data']['content'] + '\n\nKeep a backup kit.\n'
    page.locator('#draft').fill(proposed)
    page.route('**/edit-manuscript', lambda route: route.fulfill(status=503, json={'error': 'Review unavailable.'}))
    page.locator('#review').click()
    expect(page.locator('#message')).to_have_text('Review unavailable.')
    expect(page.locator('#draft')).to_have_value(proposed)
    expect(page.locator('#review')).to_be_enabled()
    expect(page.locator('#apply')).to_be_disabled()
    assert database.get_project(pid) == before


def test_browser_uncertain_save_requires_reload_instead_of_repeating_a_write(editor_browser):
    import database
    from playwright.sync_api import expect
    page, pid, client, path, requests = editor_browser
    original = database.get_project(pid)['data']['content']
    proposed = original + '\n\nCheck the printer backup before leaving.\n'
    page.locator('#draft').fill(proposed)
    page.locator('#review').click()
    expect(page.locator('#apply')).to_be_enabled()
    writes = []
    def lose_save_response(route):
        body = route.request.post_data_json
        writes.append(body['action'])
        assert client.post(path, json=body).status_code == 200
        route.abort('failed')
    page.route('**/edit-manuscript', lose_save_response)
    page.locator('#apply').click()
    expect(page.locator('#message')).to_contain_text('Reload this page')
    expect(page.locator('#apply')).to_be_disabled()
    expect(page.locator('#undo')).to_be_disabled()
    assert database.get_project(pid)['data']['content'] == proposed
    assert writes == ['apply'] and requests == ['preview']
