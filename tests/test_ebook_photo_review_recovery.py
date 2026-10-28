"""Saved photographs can be reviewed without inline full-size payloads or paid calls."""
import hashlib
import os

os.environ['FACTORY_TEST_MODE'] = '1'

import pytest
from PIL import Image
from services import ebook_visual_pipeline as vp


@pytest.fixture
def photo(tmp_path, monkeypatch):
    import app as application
    path = tmp_path / 'ebook-7' / 'visuals' / 'v_ch5.png'
    path.parent.mkdir(parents=True)
    Image.new('RGB', (1200, 800), '#82949b').save(path)
    aid = {'visual_id': 'v_ch5', 'type': 'photo', 'chapter': 'Kitchen',
           'chapter_index': 5, 'asset_path': str(path),
           'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    data = {'package_id': 'ebook-7', 'visual_plan': {'chapters': [{'aids': [aid]}]}}
    monkeypatch.setattr(vp, 'EXPORTS_DIR', str(tmp_path))
    monkeypatch.setattr(application, '_ebook_workspace_project_or_404',
                        lambda pid: ({'id': pid, 'data': data}, None))
    return application.app.test_client(), path, aid, data


def test_review_uses_lazy_image_and_rejects_unknown_chart_or_changed_bytes(photo):
    client, path, aid, _ = photo
    response = client.get('/ebook-workspace/7/review-photo/v_ch5')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '/ebook-workspace/7/visual-photo/v_ch5' in html
    assert 'data:image' not in html
    assert client.get('/ebook-workspace/7/visual-photo/v_ch5').data == path.read_bytes()
    assert client.get('/ebook-workspace/7/review-photo/absent').status_code == 404
    aid['type'] = 'chart'
    assert client.get('/ebook-workspace/7/review-photo/v_ch5').status_code == 404
    aid['type'] = 'photo'
    path.write_bytes(b'changed')
    assert client.get('/ebook-workspace/7/visual-photo/v_ch5').status_code == 404


def test_review_preserves_project_access_boundary(photo, monkeypatch):
    import app as application
    client, _, _, _ = photo
    monkeypatch.setattr(application, '_ebook_workspace_project_or_404',
                        lambda pid: (None, ('Not found', 404)))
    assert client.get('/ebook-workspace/8/review-photo/v_ch5').status_code == 404
    assert client.get('/ebook-workspace/8/visual-photo/v_ch5').status_code == 404


def test_photo_review_refuses_paths_outside_the_book_and_symlinks(photo, tmp_path):
    client, path, aid, _ = photo
    external = tmp_path / 'private.png'
    external.write_bytes(path.read_bytes())
    aid['asset_path'] = str(external)
    assert client.get('/ebook-workspace/7/visual-photo/v_ch5').status_code == 404
    aid['asset_path'] = str(path)
    path.unlink()
    path.symlink_to(external)
    assert client.get('/ebook-workspace/7/visual-photo/v_ch5').status_code == 404


def test_legacy_package_requires_an_asset_owned_by_this_project(photo, monkeypatch, tmp_path):
    import app as application
    client, path, aid, data = photo
    legacy = tmp_path / 'legacy-book' / 'visuals' / 'v_ch5.png'
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(path.read_bytes())
    data['package_id'] = 'legacy-book'
    aid['asset_path'] = str(legacy)
    monkeypatch.setattr(application.database, 'get_asset_by_key', lambda key: None)
    assert client.get('/ebook-workspace/7/visual-photo/v_ch5').status_code == 404
    monkeypatch.setattr(application.database, 'get_asset_by_key', lambda key: {'project_id': 8, 'checksum': aid['sha256']})
    assert client.get('/ebook-workspace/7/visual-photo/v_ch5').status_code == 404
    monkeypatch.setattr(application.database, 'get_asset_by_key', lambda key: {'project_id': 7, 'checksum': aid['sha256']})
    assert client.get('/ebook-workspace/7/visual-photo/v_ch5').status_code == 200


def test_accept_recovers_verified_local_file_before_evaluation(photo, monkeypatch):
    from services import ebook_workspace_actions as wsa
    _, path, aid, data = photo
    aid['asset_path'] = '/builder/missing/visuals/v_ch5.png'
    monkeypatch.setattr(vp, 'local_visual_path', lambda *a, **kw: str(path))
    monkeypatch.setattr(vp, '_assert_mutable', lambda *a, **kw: None)
    inspected = []
    monkeypatch.setattr(vp, 'stamp_plan_photo_matches',
                        lambda plan: inspected.append(plan['chapters'][0]['aids'][0]['asset_path']))
    wsa.visuals(data, {'action': 'accept-photo', 'visual_id': 'v_ch5'})
    assert inspected == [str(path)]
    assert aid['user_accepted'] and aid['seen_full_size']


@pytest.mark.parametrize('refused', [False, True, 'hard-rejection'])
def test_browser_saves_only_after_photo_load_and_reports_refusal(photo, refused):
    import json
    from playwright.sync_api import sync_playwright, expect
    client, path, _, _ = photo
    html = client.get('/ebook-workspace/7/review-photo/v_ch5').get_data(as_text=True)
    seen = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        def route(r):
            if '/visual-photo/' in r.request.url:
                return r.fulfill(content_type='image/png', body=path.read_bytes())
            if r.request.method == 'POST':
                seen.append(r.request.post_data_json)
                return r.fulfill(status=400 if refused is True else 200, content_type='application/json',
                                 body=json.dumps({'ok': refused is not True, 'error': 'Photo rejected.',
                                   'message': 'Photo rejected.' if refused else 'Accepted.',
                                   'workspace': {'design': {'visual_review': {'assets': [
                                     {'visual_id': 'v_ch5', 'user_accepted': not refused,
                                      'match_status': 'reject' if refused else 'pass'}]}}}}))
            return r.fulfill(content_type='text/html', body=html)
        page.route('**/*', route)
        page.goto('http://factory.test/ebook-workspace/7/review-photo/v_ch5')
        button = page.get_by_role('button', name='Use this photograph')
        expect(button).to_be_enabled()
        button.click()
        expect(page.get_by_role('status')).to_contain_text('Photo rejected.' if refused else 'Photograph choice saved.')
        assert seen == [{'action': 'accept-photo', 'visual_id': 'v_ch5'}]
        if refused:
            expect(button).to_be_enabled()
        browser.close()
