"""Existing drafts can be edited without billing or stale release approval."""
import copy
import pytest
from services.ebook_manuscript_editor import apply_edit, current_text, digest, preview
from services.ebook_project_workspace import build_acceptance_project_data, stage_status
from services.ebook_manuscript_fixtures import build_event_photo_strong_manuscript


@pytest.fixture
def draft():
    data = build_acceptance_project_data()
    data['content'] = data['ebook'] = build_event_photo_strong_manuscript()
    data['release_status'] = 'PASS'
    data['release_certificate'] = {'old': True}
    data['export_ready'] = True
    data['pdf_bytes'] = 'preserved-file'
    return data


def test_preview_is_read_only_and_cost_free(draft):
    before = copy.deepcopy(draft)
    original = current_text(draft)
    result = preview(draft, original + '\n\nCheck the the backup kit.\n')
    assert draft == before and result['paid_calls'] == 0
    assert result['can_apply'] and 'Check the the backup kit.' in result['diff']


def test_apply_and_undo_preserve_original_and_budget_but_not_certificates(draft):
    original = current_text(draft)
    edited = original + '\n\nCheck the backup kit.\n'
    ledger = copy.deepcopy(draft['ebook_workspace']['paid_call_ledger'])
    saved = apply_edit(draft, edited, digest(original))
    assert current_text(saved) == edited
    assert current_text(draft) == original
    assert saved['pdf_bytes'] == 'preserved-file'
    assert saved['release_certificate'] is None and not saved['export_ready']
    assert stage_status(saved['ebook_workspace'], 'manuscript') == 'awaiting_approval'
    assert saved['ebook_workspace']['paid_call_ledger'] == {**ledger, 'pending_estimate': None}
    restored = apply_edit(saved, '', digest(edited), undo=True)
    assert current_text(restored) == original
    assert restored['artifact_revision'] == saved['artifact_revision'] + 1
    assert not restored['export_ready']


def test_structural_damage_and_stale_edits_are_refused(draft):
    original = current_text(draft)
    with pytest.raises(ValueError, match='new manuscript findings'):
        apply_edit(draft, '# An unrelated short book\n\nNothing here.', digest(original))
    with pytest.raises(ValueError, match='changed'):
        apply_edit(draft, original + '\nMore.', 'stale')
    assert draft['export_ready']


def test_building_and_empty_edits_are_refused(draft):
    draft['ebook_build'] = {'stages': {'manuscript': {'status': 'RUNNING'}}}
    with pytest.raises(ValueError, match='current build'):
        apply_edit(draft, current_text(draft), digest(current_text(draft)))
    with pytest.raises(ValueError, match='empty'):
        preview(draft, '')


def test_route_preview_save_undo_and_html_escape(draft, monkeypatch):
    import database
    from app import app
    from services.jobs import store
    project = database.create_project('Editor test', 'ebook', draft, system_test=True)
    monkeypatch.setattr(store, 'get_for_project', lambda pid: None)
    client = app.test_client()
    path = f"/ebook-workspace/{project['id']}/edit-manuscript"
    page = client.get(path)
    assert page.status_code == 200 and b'Apply reviewed edits' in page.data
    original = current_text(draft)
    proposed = original + '\n\n<script>alert("x")</script>\n'
    review = client.post(path, json={'action':'preview', 'manuscript':proposed}).get_json()['review']
    assert current_text(database.get_project(project['id'])['data']) == original
    response = client.post(path, json={'action':'apply', 'manuscript':proposed,
                                      'expected_digest':review['original_sha256']})
    assert response.status_code == 200
    assert b'&lt;script&gt;' in client.get(path).data
    response = client.post(path, json={'action':'undo', 'expected_digest':digest(proposed)})
    assert response.status_code == 200 and response.get_json()['manuscript'] == original
    monkeypatch.setattr(store, 'get_for_project', lambda pid: {'status':'QUEUED'})
    assert client.post(path, json={'action':'apply', 'manuscript':proposed,
                                  'expected_digest':digest(original)}).status_code == 409


def test_browser_editor_review_apply_and_undo(draft, monkeypatch):
    import database
    import json
    from app import app
    from services.jobs import store
    from playwright.sync_api import sync_playwright
    monkeypatch.setattr(store, 'get_for_project', lambda pid: None)
    project = database.create_project('Browser editor', 'ebook', draft, system_test=True)
    client = app.test_client()
    path = f"/ebook-workspace/{project['id']}/edit-manuscript"
    original = current_text(draft)
    edited = original + '\n\nCheck the backup kit before leaving.\n'
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=['--no-sandbox'])
        page = browser.new_page()
        def handle(route):
            req = route.request
            response = client.open(path, method=req.method,
                json=json.loads(req.post_data) if req.post_data else None)
            route.fulfill(status=response.status_code, body=response.data,
                          content_type=response.content_type)
        page.route('http://editor.test/**', handle)
        page.goto('http://editor.test' + path)
        page.get_by_label('Manuscript (Markdown)').fill(edited)
        page.get_by_role('button', name='Review my edits', exact=True).click()
        page.get_by_role('button', name='Apply reviewed edits', exact=True).click()
        page.get_by_text('Saved. Review and approve this manuscript before rebuilding final files.', exact=True).wait_for()
        assert current_text(database.get_project(project['id'])['data']) == edited
        page.get_by_role('button', name='Undo last saved edit', exact=True).click()
        page.wait_for_function("document.getElementById('draft').value === " + json.dumps(original))
        assert current_text(database.get_project(project['id'])['data']) == original
        browser.close()


def test_repair_clears_real_findings_and_undo_restores_gate(draft):
    valid = current_text(draft)
    draft['content'] = draft['ebook'] = valid + '\n\n## Chapter Extra\n\nsub-goal #1 invent a Lonnie story here\n'
    broken = current_text(draft)
    report = preview(draft, valid)
    assert report['can_apply']
    repaired = apply_edit(draft, valid, digest(broken))
    assert stage_status(repaired['ebook_workspace'], 'manuscript') == 'awaiting_approval'
    restored = apply_edit(repaired, '', digest(valid), undo=True)
    assert current_text(restored) == broken
    assert stage_status(restored['ebook_workspace'], 'manuscript') == 'needs_correction'
    assert restored['ebook_workspace']['manuscript_qa']
    assert not restored['export_ready']


def test_incomplete_chapter_can_be_improved_in_several_edits(draft):
    import re
    from services.ebook_manuscript_engine import validate_manuscript_quality
    text = current_text(draft)
    heading = re.search(r'^## .+\n', text, re.M)
    next_heading = re.search(r'^## .+\n', text[heading.end():], re.M)
    start, end = heading.end(), heading.end() + next_heading.start()
    thin = text[:start] + '\nEvent photography needs careful planning before guests arrive.\n\n' + text[end:]
    improved = thin.replace('before guests arrive.', 'before guests arrive. Check the camera and printer backup kit before traveling to the venue.')
    draft['content'] = draft['ebook'] = thin
    assert validate_manuscript_quality(draft).status != 'PASS'
    report = preview(draft, improved)
    assert report['can_apply'] and not report['new_findings']
    saved = apply_edit(draft, improved, digest(thin))
    assert current_text(saved) == improved
    assert stage_status(saved['ebook_workspace'], 'manuscript') == 'needs_correction'
