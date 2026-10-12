import copy
from unittest.mock import patch

from app import app
import database
from services.ebook_project_workspace import new_workspace, edit_author, set_stage_status, stage_status
from services.ebook_build_orchestrator import _prepare_cover
from services.ebook_photo_cover import PhotoCoverError
import pytest


def saved_book():
    ws = new_workspace(topic='Eco Home')
    for stage in ('research', 'title', 'outline', 'manuscript', 'visuals', 'cover', 'design', 'preview', 'preflight', 'export'):
        set_stage_status(ws, stage, 'approved')
    return {
        'product_type': 'ebook', 'ebook_project_workspace': True, 'ebook_workspace': ws,
        'title': 'Eco Home', 'subtitle': 'Room by room',
        'content': '## Chapter 1\n\nKeep this manuscript exactly.',
        'ebook': '## Chapter 1\n\nKeep this manuscript exactly.',
        'visual_plan': {'chapters': [{'aids': [{'type': 'photo', 'asset_path': '/saved/photo.jpg', 'pexels': {'photo_id': '99'}, 'match_status': 'pass'}]}]},
        'cover_design': {'selected_layout': 'old'}, 'export_ready': True,
        'ebook_build': {'failed': True, 'finished': True, 'stages': {'visuals': {'attempts': 2, 'status': 'done'}, 'cover': {'attempts': 3}}},
    }


def test_author_edit_preserves_manuscript_and_resolved_visuals():
    data = saved_book()
    before = copy.deepcopy(data)
    result = edit_author(data, author=' Lonnie Brown ')
    assert result['author_brand'] == result['ebook_workspace']['author'] == 'Lonnie Brown'
    assert result['fields']['author_brand'] == 'Lonnie Brown'
    assert result['content'] == before['content']
    assert result['ebook'] == before['ebook']
    assert result['visual_plan'] == before['visual_plan']
    for stage in ('research', 'title', 'outline', 'manuscript', 'visuals'):
        assert stage_status(result['ebook_workspace'], stage) == 'approved'
    assert result['ebook_build']['stages']['visuals'] == before['ebook_build']['stages']['visuals']
    for stage in ('cover', 'design', 'preview', 'preflight', 'export'):
        assert stage_status(result['ebook_workspace'], stage) == 'not_started'
    assert result['cover_design'] is None
    assert not result['export_ready']
    again = edit_author(copy.deepcopy(result), author='Lonnie Brown')
    assert again == result


def test_route_saves_author_and_refuses_blank():
    project = database.create_project('Author recovery', 'ebook', saved_book())
    client = app.test_client()
    url = f"/ebook-workspace/{project['id']}/author"
    assert client.post(url, json={'author': ' '}).status_code == 400
    response = client.post(url, json={'author': 'Lonnie Brown'})
    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json()['workspace']['author'] == 'Lonnie Brown'
    stored = database.get_project(project['id'])['data']
    assert stored['author_brand'] == 'Lonnie Brown'
    assert stored['visual_plan'] == saved_book()['visual_plan']
    assert client.post('/ebook-workspace/99999999/author', json={'author': 'Lonnie Brown'}).status_code == 404


def test_missing_author_refuses_before_stock_search():
    with patch('services.ebook_customer_path.complete_photo_cover') as stock:
        with pytest.raises(PhotoCoverError, match='author name'):
            _prepare_cover(saved_book(), 20)
        stock.assert_not_called()


@pytest.mark.parametrize('state', ['APPROVED', 'LOCKED'])
def test_author_edit_refuses_protected_artifacts(state):
    data = saved_book()
    data['artifact_state'] = state
    before = copy.deepcopy(data)
    with pytest.raises(ValueError):
        edit_author(data, author='Lonnie Brown')
    assert data == before
