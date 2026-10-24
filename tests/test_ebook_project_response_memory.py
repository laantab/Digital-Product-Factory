"""Workspace navigation must not serialize the entire rendered book again."""
import copy

import app as app_module


def test_workspace_detail_omits_preview_and_review_pixels_without_mutating_source(monkeypatch):
    pixels = 'image-data-' * 200000
    data = {
        'ebook_project_workspace': True, 'ebook_workspace': {},
        'content': 'Approved manuscript', 'pdf_bytes': 'preserved legacy PDF',
        'preview_html': pixels, 'ebook_preview_html': pixels,
        'release_review': {'status': 'Changes required', 'decisions': {'10': 'reject'},
                           'base': {'visuals': [{'page': 10, 'thumb_b64': pixels}],
                                    'findings': [{'code': 'CHART_NOT_A_SEQUENCE'}]}},
    }
    project = {'id': 123, 'type': 'ebook', 'data': data}
    original = copy.deepcopy(project)
    monkeypatch.setattr(app_module.database, 'get_project', lambda _: project)
    def enrich(p, **_):
        # Readiness must still inspect the real preview, before projection.
        assert p['data']['preview_html'] == pixels
        assert p['data']['release_review']['base']['visuals'][0]['thumb_b64'] == pixels
        return p
    monkeypatch.setattr(app_module, '_enrich_project_artifact_fields', enrich)
    response = app_module.app.test_client().get('/projects/123')
    assert response.status_code == 200
    result = response.get_json()['data']
    assert len(response.data) < 2000
    assert result['content'] == data['content']
    assert result['pdf_bytes'] == data['pdf_bytes']
    assert result['release_review']['decisions'] == {'10': 'reject'}
    assert result['release_review']['base']['findings'] == data['release_review']['base']['findings']
    assert project == original


def test_legacy_product_detail_remains_complete(monkeypatch):
    project = {'id': 124, 'type': 'ebook', 'data': {
        'preview_html': '<h1>Customer preview</h1>', 'content': 'Original',
        'release_review': {'base': {'visuals': [{'thumb_b64': 'original'}]}},
    }}
    monkeypatch.setattr(app_module.database, 'get_project', lambda _: project)
    monkeypatch.setattr(app_module, '_enrich_project_artifact_fields', lambda p, **_: p)
    response = app_module.app.test_client().get('/projects/124')
    assert response.status_code == 200
    assert response.get_json() == project
